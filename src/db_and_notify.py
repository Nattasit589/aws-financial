"""db_and_notify.py — จัดการ Watchlist / Smart Cache บน Amazon DynamoDB และส่งอีเมลผ่าน Amazon SNS

Single-Table Design:
- Watchlist : pk = WORKSPACE#{workspace_id}, sk = WATCHLIST
- ผลวิเคราะห์: pk = WORKSPACE#{workspace_id}, sk = ANALYSIS#{symbol}#{persona} (มี TTL)
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal

TABLE_NAME = os.environ.get("PORTFOLIO_TABLE", "PortfolioTable")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "10"))
DEFAULT_PERSONA = "dividend"
VALID_PERSONAS = ("dividend", "momentum")

_resource = None
_table = None
_sns = None


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
        "analysis_data": to_jsonable(analysis),
        "analyzed_at": analysis.get("analyzed_at") or _now_iso(),
        "ttl": ttl,
    }
    _dynamo_table().put_item(Item=item)


def delete_analysis(workspace_id: str, symbol: str, persona: str) -> None:
    _dynamo_table().delete_item(
        Key=_analysis_key(normalize_workspace(workspace_id), symbol, persona)
    )


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
    """อารมณ์ข่าว + หัวข้อข่าวล่าสุด ต่อท้ายรายละเอียดของหุ้นแต่ละตัว"""
    ai = result.get("ai") or {}
    tone = str(ai.get("news_tone") or "").strip() or "-"
    news = result.get("news") or []
    lines = [f"  อารมณ์ข่าว: {tone}"]
    titles = [line for line in (_headline(item) for item in news[:limit]) if line]
    if titles:
        lines.append("  ข่าวล่าสุด:")
        lines.extend(f"    - {line}" for line in titles)
    else:
        lines.append("  ข่าวล่าสุด: ไม่พบข่าวในรอบนี้")
    return lines


def build_report_email(workspace_id: str, persona: str, results: list[dict], summary: dict) -> tuple[str, str]:
    persona_label = "สายปันผลเน้นปลอดภัย" if persona == "dividend" else "สายเก็งกำไรระยะสั้น"
    subject = f"[AI Equity Co-Pilot] Portfolio report: {workspace_id}"
    counts = summary.get("counts", {})
    risks = summary.get("risk_counts", {})

    lines = [
        f"AI Equity Co-Pilot — รายงานสรุปพอร์ต {workspace_id}",
        f"โหมดนักลงทุน: {persona_label}",
        f"คะแนนเฉลี่ยพอร์ต: {summary.get('avg_score', 0)}/100",
        f"สัญญาณ: BUY {counts.get('BUY', 0)} | WATCH {counts.get('WATCH', 0)} | SELL {counts.get('SELL', 0)}",
        (
            "ความเสี่ยง: ต่ำ {low} | ปานกลาง {mid} | สูง {high}".format(
                low=risks.get("LOW", 0), mid=risks.get("MEDIUM", 0), high=risks.get("HIGH", 0)
            )
        ),
        f"บทสรุปภาพรวม: {summary.get('verdict', '-')}",
        f"ต้นทุน AI รอบนี้: {summary.get('total_cost_thb', 0):.4f} บาท",
        "",
        "สรุปเร็ว:",
    ]

    for result in results:
        ai = result.get("ai") or {}
        if result.get("error") or not ai:
            continue
        indicators = result.get("indicators") or {}
        change = indicators.get("change_pct")
        change_text = f"{float(change):+.2f}%" if change is not None else "n/a"
        risk_label = RISK_LABELS.get(str(ai.get("risk_level") or "MEDIUM").upper(), "ปานกลาง")
        lines.append(
            f"  {result.get('symbol', '-'):<8} {str(ai.get('signal', 'WATCH')):<5} "
            f"{int(ai.get('score') or 0):>3}/100  {change_text:>8}  เสี่ยง{risk_label}"
        )

    lines.extend(["", "รายละเอียดรายตัว:"])

    for result in results:
        ai = result.get("ai") or {}
        if result.get("error") or not ai:
            continue  # หุ้นที่ดึงข้อมูลไม่สำเร็จถูกข้ามไปแล้วในสรุปเร็ว
        indicators = result.get("indicators") or {}
        lines.extend(
            [
                f"- {result.get('symbol')} ({result.get('name', '')})",
                f"  คะแนน {ai.get('score', 0)}/100 | สัญญาณ {ai.get('signal', '-')} | "
                f"ราคา {indicators.get('price', '-')} {result.get('currency', '')}",
                f"  ความเสี่ยง: {RISK_LABELS.get(str(ai.get('risk_level') or 'MEDIUM').upper(), 'ปานกลาง')}"
                f" — {'; '.join(ai.get('risk_reasons', [])[:2]) or '-'}",
                f"  สรุป: {ai.get('trend_summary', '-')}",
                f"  จุดเข้า: {ai.get('action_plan', {}).get('entry_zone', '-')} | "
                f"ตัดขาดทุน: {ai.get('action_plan', {}).get('stop_loss', '-')} | "
                f"ทำกำไร: {ai.get('action_plan', {}).get('take_profit', '-')}",
                f"  ความเสี่ยง: {'; '.join(ai.get('risks', []))}",
            ]
        )
        lines.extend(_news_lines(result))
        lines.append("")

    lines.append("ข้อมูลนี้เป็นเครื่องมือช่วยวิเคราะห์ ไม่ใช่คำแนะนำการลงทุน")
    return subject, "\n".join(lines)
