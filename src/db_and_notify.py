"""db_and_notify.py — จัดการ Watchlist / Smart Cache บน Amazon DynamoDB,
เก็บสำเนารายงานบน Amazon S3 และส่งอีเมลผ่าน Amazon SNS

Single-Table Design:
- Watchlist : pk = WORKSPACE#{workspace_id}, sk = WATCHLIST
- ผลวิเคราะห์: pk = WORKSPACE#{workspace_id}, sk = ANALYSIS#{symbol}#{persona} (มี TTL)

S3 Layout (สำเนารายงานไว้ตรวจย้อนหลัง):
- reports/{workspace_id}/{YYYY-MM-DD}/{manual|scheduled}.json
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

logger = logging.getLogger("equity-copilot.storage")

TABLE_NAME = os.environ.get("PORTFOLIO_TABLE", "PortfolioTable")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
REPORT_BUCKET = os.environ.get("REPORT_BUCKET", "")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "10"))
DEFAULT_PERSONA = "dividend"
VALID_PERSONAS = ("dividend", "momentum")

_resource = None
_table = None
_sns = None
_s3 = None


class WorkspaceError(Exception):
    """ข้อผิดพลาดเกี่ยวกับ Workspace ที่แสดงให้ผู้ใช้เห็นเป็นภาษาไทย"""


class NotifyError(Exception):
    """ส่งอีเมลไม่สำเร็จ"""


def _dynamo_table():
    global _resource, _table
    if _table is None:
        import boto3

        _resource = boto3.resource("dynamodb")
        _table = _resource.Table(TABLE_NAME)
    return _table


def _sns_client():
    global _sns
    if _sns is None:
        import boto3

        _sns = boto3.client("sns")
    return _sns


def _s3_client():
    global _s3
    if _s3 is None:
        import boto3

        _s3 = boto3.client("s3")
    return _s3


def normalize_workspace(raw: str) -> str:
    workspace_id = re.sub(r"[^A-Za-z0-9_-]", "", (raw or "").strip()).upper()
    if not workspace_id:
        raise WorkspaceError("กรุณาระบุ Workspace Code (ตัวอักษรอังกฤษ ตัวเลข - หรือ _)")
    return workspace_id[:32]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _watchlist_key(workspace_id: str) -> dict[str, str]:
    return {"pk": f"WORKSPACE#{workspace_id}", "sk": "WATCHLIST"}


def _analysis_key(workspace_id: str, symbol: str, persona: str) -> dict[str, str]:
    return {"pk": f"WORKSPACE#{workspace_id}", "sk": f"ANALYSIS#{symbol}#{persona}"}


def to_jsonable(value):
    """แปลง Decimal ของ DynamoDB ให้เป็น float/int เพื่อให้ JSONResponse ส่งออกได้"""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def _to_dynamodb(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(key): _to_dynamodb(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dynamodb(item) for item in value]
    return value


# --------------------------------------------------------------------------
# Watchlist
# --------------------------------------------------------------------------
def get_watchlist(workspace_id: str) -> dict:
    workspace_id = normalize_workspace(workspace_id)
    item = _dynamo_table().get_item(Key=_watchlist_key(workspace_id)).get("Item") or {}
    persona = str(item.get("persona") or DEFAULT_PERSONA)
    return {
        "workspace_id": workspace_id,
        "symbols": [str(symbol) for symbol in (item.get("symbols") or [])],
        "persona": persona if persona in VALID_PERSONAS else DEFAULT_PERSONA,
        "updated_at": str(item.get("updated_at") or ""),
    }


def save_watchlist(workspace_id: str, symbols: list[str], persona: str) -> dict:
    workspace_id = normalize_workspace(workspace_id)
    persona = persona if persona in VALID_PERSONAS else DEFAULT_PERSONA
    payload = {
        **_watchlist_key(workspace_id),
        "symbols": symbols[:MAX_SYMBOLS],
        "persona": persona,
        "updated_at": _now_iso(),
    }
    _dynamo_table().put_item(Item=payload)
    return {
        "workspace_id": workspace_id,
        "symbols": list(payload["symbols"]),
        "persona": persona,
        "updated_at": payload["updated_at"],
    }


def add_symbol(workspace_id: str, symbol: str, persona: str | None = None) -> dict:
    workspace = get_watchlist(workspace_id)
    if symbol in workspace["symbols"]:
        raise WorkspaceError(f"{symbol} อยู่ในพอร์ตนี้แล้ว")
    if len(workspace["symbols"]) >= MAX_SYMBOLS:
        raise WorkspaceError(f"พอร์ตนี้มีหุ้นครบ {MAX_SYMBOLS} ตัวแล้ว กรุณาลบตัวที่ไม่ใช้ก่อน")
    symbols = workspace["symbols"] + [symbol]
    return save_watchlist(workspace_id, symbols, persona or workspace["persona"])


def remove_symbol(workspace_id: str, symbol: str) -> dict:
    workspace = get_watchlist(workspace_id)
    if symbol not in workspace["symbols"]:
        raise WorkspaceError(f"ไม่พบ {symbol} ในพอร์ตนี้")
    symbols = [item for item in workspace["symbols"] if item != symbol]
    return save_watchlist(workspace_id, symbols, workspace["persona"])


def list_workspaces() -> list[str]:
    """ใช้ในงานอัตโนมัติของ EventBridge: ดึง Workspace ทั้งหมดที่มี Watchlist"""
    from boto3.dynamodb.conditions import Attr

    table = _dynamo_table()
    workspaces: list[str] = []
    kwargs = {
        "FilterExpression": Attr("sk").eq("WATCHLIST"),
        "ProjectionExpression": "pk",
    }
    while True:
        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            pk = str(item.get("pk") or "")
            if pk.startswith("WORKSPACE#"):
                workspaces.append(pk.replace("WORKSPACE#", "", 1))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(set(workspaces))


# --------------------------------------------------------------------------
# Smart Cache (TTL)
# --------------------------------------------------------------------------
def get_cached_analysis(workspace_id: str, symbol: str, persona: str) -> dict | None:
    item = _dynamo_table().get_item(
        Key=_analysis_key(normalize_workspace(workspace_id), symbol, persona)
    ).get("Item")
    if not item:
        return None

    ttl = item.get("ttl")
    if ttl is not None and int(ttl) < int(time.time()):
        return None

    analysis = to_jsonable(item.get("analysis_data"))
    if not isinstance(analysis, dict) or not analysis.get("ai"):
        return None

    analysis["cache_hit"] = True
    return analysis


def put_analysis(workspace_id: str, symbol: str, persona: str, analysis: dict) -> None:
    ttl = int(time.time()) + CACHE_TTL_SECONDS
    item = {
        **_analysis_key(normalize_workspace(workspace_id), symbol, persona),
        "analysis_data": _to_dynamodb(analysis),
        "analyzed_at": analysis.get("analyzed_at") or _now_iso(),
        "ttl": ttl,
    }
    _dynamo_table().put_item(Item=item)


def delete_analysis(workspace_id: str, symbol: str, persona: str) -> None:
    _dynamo_table().delete_item(
        Key=_analysis_key(normalize_workspace(workspace_id), symbol, persona)
    )


# --------------------------------------------------------------------------
# Amazon S3
# --------------------------------------------------------------------------
def export_report_json(
    workspace_id: str,
    persona: str,
    results: list[dict],
    summary: dict,
    report_kind: str = "manual",
) -> str:
    """เก็บสำเนารายงานรอบนี้เป็น JSON ลง S3 แล้วคืนค่า s3://bucket/key

    การเก็บสำเนาต้องไม่ทำให้การส่งอีเมลล้มเหลว: ถ้าไม่มี bucket ตั้งค่าไว้หรือ
    เขียนไม่สำเร็จ (เช่นสิทธิ์ S3 ไม่พอ) จะคืน "" และเขียน log ไว้แทน
    """
    if not REPORT_BUCKET:
        return ""
    try:
        workspace = normalize_workspace(workspace_id)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"reports/{workspace}/{day}/{report_kind}.json"
        payload = {
            "workspace_id": workspace,
            "persona": persona,
            "report_kind": report_kind,
            "generated_at": _now_iso(),
            "summary": summary,
            "results": results,
        }
        body = json.dumps(to_jsonable(payload), ensure_ascii=False).encode("utf-8")
        _s3_client().put_object(
            Bucket=REPORT_BUCKET,
            Key=key,
            Body=body,
            ContentType="application/json; charset=utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - เก็บสำเนาไม่สำเร็จต้องไม่ล้มรายงาน
        logger.warning("เก็บสำเนารายงานลง S3 ไม่สำเร็จ: %s", exc.__class__.__name__)
        return ""
    return f"s3://{REPORT_BUCKET}/{key}"


# --------------------------------------------------------------------------
# Amazon SNS
# --------------------------------------------------------------------------
def send_email(subject: str, message: str) -> str:
    """ส่งอีเมลผ่าน SNS (Subject ต้องเป็น ASCII ตามข้อจำกัดของ SNS)"""
    if not SNS_TOPIC_ARN:
        raise NotifyError("ยังไม่ได้ตั้งค่า SNS_TOPIC_ARN ใน environment ของ Lambda")
    try:
        response = _sns_client().publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
    except Exception as exc:  # noqa: BLE001
        raise NotifyError(f"ส่งอีเมลผ่าน SNS ไม่สำเร็จ: {exc.__class__.__name__}") from exc
    return str(response.get("MessageId") or "")


RISK_LABELS = {"LOW": "ต่ำ", "MEDIUM": "ปานกลาง", "HIGH": "สูง"}

# อีโมจิช่วยให้สแกนอีเมล plain-text ได้เร็ว (SNS ส่งได้เฉพาะข้อความ ไม่มี HTML)
SIGNAL_EMOJI = {"BUY": "🟢", "WATCH": "🟡", "SELL": "🔴"}
RISK_EMOJI = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}
TONE_EMOJI = {"บวก": "🟢", "กลาง": "🟡", "ลบ": "🔴"}
SOURCE_LABELS = {
    "bedrock": "🤖 Bedrock AI",
    "gemini_fallback": "✨ Gemini (AI สำรอง)",
    "rule_fallback": "📐 กฎเทคนิค (ไม่ใช่ AI)",
}
RULE = "━" * 34


def _signal_emoji(value) -> str:
    return SIGNAL_EMOJI.get(str(value or "").upper(), "⚪")


def _risk_emoji(value) -> str:
    return RISK_EMOJI.get(str(value or "").upper(), "⚪")


def _tone_emoji(value) -> str:
    return TONE_EMOJI.get(str(value or "").strip(), "⚪")


def _bullet_lines(items, empty: str) -> list[str]:
    texts = [str(item).strip() for item in (items or []) if str(item).strip()]
    if not texts:
        return [f"      • {empty}"]
    return [f"      • {text}" for text in texts]


def _headline(item: dict, limit: int = 110) -> str:
    """จัดบรรทัดหัวข้อข่าว 1 บรรทัด (ตัดยาวเกินไปเพื่อให้อ่านง่ายในอีเมล)"""
    title = str((item or {}).get("title") or "").strip()
    if not title:
        return ""
    if len(title) > limit:
        title = title[: limit - 3].rstrip() + "..."
    source = str(item.get("source") or item.get("origin") or "").strip()
    return f"{title} ({source})" if source else title


def _news_lines(result: dict, limit: int = 3) -> list[str]:
    """อารมณ์ข่าว + ข่าวที่ AI คัดว่าสำคัญ ต่อท้ายรายละเอียดของหุ้นแต่ละตัว"""
    ai = result.get("ai") or {}
    tone = str(ai.get("news_tone") or "").strip() or "-"
    picks = [pick for pick in (ai.get("news_picks") or [])[:limit] if _headline(pick)]
    news = result.get("news") or []
    lines = [f"   📰 อารมณ์ข่าว: {_tone_emoji(tone)} {tone}"]

    if picks:
        lines.append("   🔎 ข่าวที่ AI ให้ความสำคัญ:")
        for pick in picks:
            lines.append(f"      • {_headline(pick)}")
            why = str(pick.get("why") or "").strip()
            if why:
                lines.append(f"        ↳ {why}")
        return lines

    titles = [line for line in (_headline(item) for item in news[:limit]) if line]
    if titles:
        lines.append("   🗞 ข่าวล่าสุด:")
        lines.extend(f"      • {line}" for line in titles)
    else:
        lines.append("      • ไม่พบข่าวในรอบนี้")
    return lines


def _stock_block(result: dict) -> list[str]:
    """รายละเอียดหุ้น 1 ตัว จัดเป็นกลุ่มบรรทัดที่อ่านด้วยตารางตาได้"""
    ai = result.get("ai") or {}
    indicators = result.get("indicators") or {}
    plan = ai.get("action_plan") or {}
    signal = str(ai.get("signal") or "WATCH").upper()
    risk_key = str(ai.get("risk_level") or "MEDIUM").upper()
    risk_label = RISK_LABELS.get(risk_key, "ปานกลาง")
    change = indicators.get("change_pct")
    change_text = f"{float(change):+.2f}%" if change is not None and str(change) != "" else "n/a"
    price = indicators.get("price", "-")
    currency = result.get("currency") or ""

    lines = [
        f"{_signal_emoji(signal)} {result.get('symbol', '-')}"
        + (f" · {result.get('name')}" if result.get("name") else ""),
        f"   💵 ราคา {price} {currency} ({change_text} เทียบวันก่อน)",
        f"   🎯 คะแนน {ai.get('score', 0)}/100 · สัญญาณ {signal} · ความเสี่ยง {_risk_emoji(risk_key)}{risk_label}",
    ]

    summary_text = str(ai.get("trend_summary") or "").strip()
    if summary_text:
        lines.append(f"   🧭 มุมมอง: {summary_text}")

    reasons = [str(reason).strip() for reason in (ai.get("risk_reasons") or [])[:2] if str(reason).strip()]
    if reasons:
        lines.append(f"   ❗ เหตุผลความเสี่ยง: {' · '.join(reasons)}")

    lines.append(
        f"   🎛 แผนเทรด: เข้า {plan.get('entry_zone') or '-'} · "
        f"ตัดขาดทุน {plan.get('stop_loss') or '-'} · เป้าทำกำไร {plan.get('take_profit') or '-'}"
    )
    lines.append("   ✅ ปัจจัยสนับสนุน:")
    lines.extend(_bullet_lines(ai.get("catalysts"), "ยังไม่มีปัจจัยบวกที่ชัดเจนในรอบนี้"))
    lines.append("   ⚠️ ความเสี่ยงที่ต้องระวัง:")
    lines.extend(_bullet_lines(ai.get("risks"), "ไม่มีสัญญาณเสี่ยงเด่นในรอบนี้"))
    lines.extend(_news_lines(result))

    cost_thb = float((result.get("cost") or {}).get("thb") or 0.0)
    source = str(result.get("source") or "")
    meta = [SOURCE_LABELS.get(source, "🤖 AI")]
    if result.get("model_id") and source != "rule_fallback":  # กฎเทคนิคไม่ได้ใช้โมเดล
        meta.append(str(result["model_id"]))
    meta.append(f"ต้นทุนผลนี้ {cost_thb:.4f} บาท")
    if result.get("cache_hit"):
        meta.append("ใช้ผลจาก Smart Cache")
    lines.append(f"   🧾 {' · '.join(meta)}")
    return lines


def build_report_email(
    workspace_id: str,
    persona: str,
    results: list[dict],
    summary: dict,
    archive_uri: str = "",
) -> tuple[str, str]:
    """สร้างอีเมล plain-text ที่สแกนด้วยตาได้เร็ว: อีโมจิ + หัวข้อคั่น + สรุปก่อน รายละเอียดทีหลัง

    Subject ต้องเป็น ASCII เท่านั้น (ข้อจำกัดของ SNS) จึงไม่ใส่อีโมจิในหัวข้ออีเมล
    """
    persona_label = "สายปันผลเน้นปลอดภัย" if persona == "dividend" else "สายเก็งกำไรระยะสั้น"
    stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
    subject = f"[AI Equity Co-Pilot] Portfolio report {workspace_id}"
    counts = summary.get("counts", {})
    risks = summary.get("risk_counts", {})

    valid = [item for item in results if item.get("ai") and not item.get("error")]
    failed = [item for item in results if item.get("error") or not item.get("ai")]

    lines = [
        f"📊 AI Equity Co-Pilot · รายงานสรุปพอร์ต {workspace_id}",
        RULE,
        f"🕒 {stamp} น. (เวลาไทย)",
        f"🧭 โหมดนักลงทุน: {persona_label}",
        f"🎯 คะแนนเฉลี่ยพอร์ต: {summary.get('avg_score', 0)}/100 "
        f"(วิเคราะห์สำเร็จ {summary.get('analyzed_count', len(valid))} หุ้น)",
        (
            f"📈 สัญญาณ: {_signal_emoji('BUY')} BUY {counts.get('BUY', 0)} · "
            f"{_signal_emoji('WATCH')} WATCH {counts.get('WATCH', 0)} · "
            f"{_signal_emoji('SELL')} SELL {counts.get('SELL', 0)}"
        ),
        (
            f"🛡️ ความเสี่ยง: {_risk_emoji('LOW')}ต่ำ {risks.get('LOW', 0)} · "
            f"{_risk_emoji('MEDIUM')}ปานกลาง {risks.get('MEDIUM', 0)} · "
            f"{_risk_emoji('HIGH')}สูง {risks.get('HIGH', 0)}"
        ),
        f"💰 ต้นทุน AI รอบนี้: {summary.get('total_cost_thb', 0):.4f} บาท",
        f"🧠 บทสรุป: {summary.get('verdict', '-')}",
        "",
        f"📋 สรุปเร็ว (1 บรรทัดต่อหุ้น)",
        "─" * 34,
    ]

    for result in valid:
        ai = result.get("ai") or {}
        indicators = result.get("indicators") or {}
        change = indicators.get("change_pct")
        change_text = f"{float(change):+.2f}%" if change is not None and str(change) != "" else "n/a"
        risk_key = str(ai.get("risk_level") or "MEDIUM").upper()
        signal = str(ai.get("signal") or "WATCH").upper()
        cache_mark = " ⚡" if result.get("cache_hit") else ""
        lines.append(
            f"{_signal_emoji(signal)} {result.get('symbol', '-')} · {signal} · "
            f"{int(ai.get('score') or 0)}/100 · {change_text} · "
            f"เสี่ยง{RISK_LABELS.get(risk_key, 'ปานกลาง')}{cache_mark}"
        )

    if valid:
        lines.extend(["", "🔍 รายละเอียดรายตัว", RULE])
        for index, result in enumerate(valid):
            if index:
                lines.append("")
            lines.extend(_stock_block(result))

    if failed:
        lines.extend(["", "⚠️ หุ้นที่วิเคราะห์ไม่สำเร็จในรอบนี้", RULE])
        for item in failed:
            lines.append(f"❌ {item.get('symbol', '-')} — {item.get('error') or 'ไม่มีผลวิเคราะห์'}")

    lines.extend(["", RULE])
    if archive_uri:
        lines.append(f"📎 สำเนารายงาน (JSON บน Amazon S3): {archive_uri}")
        lines.append("   เปิดดูไฟล์ได้จากคอนโซล S3 หรือ AWS CLI (aws s3 cp)")
    lines.append(f"ℹ️ ข้อมูลนี้เป็นเครื่องมือช่วยวิเคราะห์ ไม่ใช่คำแนะนำการลงทุน · สร้างโดย AI Equity Co-Pilot")
    return subject, "\n".join(lines)
