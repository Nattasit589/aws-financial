"""analyzer.py — สร้าง Prompt ตาม Investor Persona, เรียก Amazon Bedrock (Converse API)
และคำนวณต้นทุน Token จริงต่อการวิเคราะห์ 1 ครั้ง

ใช้ ``bedrock-runtime.converse`` ซึ่งเป็น API กลางที่ใช้โค้ดชุดเดียวกันได้ทั้ง
ตระกูล Amazon Nova และ Anthropic Claude จึงสลับโมเดลผ่าน Parameter ได้โดยไม่ต้องแก้โค้ด
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
USD_TO_THB = float(os.environ.get("USD_TO_THB", "36.0"))
MAX_OUTPUT_TOKENS = 1200
VALID_PERSONAS = ("dividend", "momentum")
VALID_SIGNALS = ("BUY", "WATCH", "SELL")

# ราคาต่อ 1,000,000 tokens (USD) — ใช้คำนวณ Unit Economics จริงในหน้าเว็บ
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "amazon.nova-micro": (0.035, 0.14),
    "amazon.nova-lite": (0.06, 0.24),
    "amazon.nova-pro": (0.80, 3.20),
    "anthropic.claude-3-haiku": (0.25, 1.25),
    "anthropic.claude-3-5-haiku": (0.80, 4.00),
}

SYSTEM_PROMPTS: dict[str, str] = {
    "dividend": (
        "คุณคือนักวิเคราะห์การลงทุนระดับมืออาชีพสายปันผล (Conservative Dividend Investor) "
        "ที่ปรึกษานักลงทุนรายย่อยไทยอย่างตรงไปตรงมา ให้ความสำคัญกับความมั่นคงของธุรกิจ "
        "กระแสเงินสด เงินปันผล แนวรับที่ปลอดภัย และการถือครองระยะกลางถึงยาว "
        "หลีกเลี่ยงคำแนะนำที่เสี่ยงเกินไป และต้องตอบกลับเป็น JSON ที่ถูกต้องเท่านั้น ห้ามมีข้อความอื่นนอก JSON"
    ),
    "momentum": (
        "คุณคือนักวิเคราะห์เทคนิคสายเก็งกำไรระยะสั้น (Short-Term Momentum Trader) "
        "ที่ปรึกษานักลงทุนรายย่อยไทยอย่างตรงไปตรงมา ให้ความสำคัญกับจังหวะเทคนิค โมเมนตัมราคา "
        "ปริมาณซื้อขาย กระแสข่าวที่เร่งราคา จุดเข้าทำกำไร และจุดตัดขาดทุนที่ชัดเจน "
        "กล้าตัดสินใจ แต่ต้องอธิบายเหตุผลจากตัวเลขที่ให้มาเท่านั้น และต้องตอบกลับเป็น JSON ที่ถูกต้อง ห้ามมีข้อความอื่นนอก JSON"
    ),
}

_RESPONSE_SCHEMA = """{
  "score": ตัวเลข 0-100 (ความน่าสนใจโดยรวม),
  "signal": "BUY" หรือ "WATCH" หรือ "SELL",
  "news_tone": "บวก" หรือ "กลาง" หรือ "ลบ" (อารมณ์ของข่าวล่าสุดที่มีต่อหุ้นตัวนี้),
  "trend_summary": "สรุปแนวโน้ม 1-2 ประโยคภาษาไทย",
  "action_plan": {
    "entry_zone": "กรอบราคาที่ควรเข้าซื้อ (ข้อความสั้น)",
    "stop_loss": "จุดตัดขาดทุน (ข้อความสั้น)",
    "take_profit": "เป้าหมายทำกำไร (ข้อความสั้น)",
    "checklist": ["เช็กลิสต์ 3 ข้อ ภาษาไทย", "...", "..."]
  },
  "catalysts": ["ปัจจัยบวก 2-3 ข้อ ภาษาไทย"],
  "risks": ["ความเสี่ยง 2-3 ข้อ ภาษาไทย"],
  "news_picks": [
    {"title": "คัดลอกหัวข้อข่าวจากรายการด้านบนให้ตรงตัวอักษร", "why": "เหตุผล 1 ประโยคว่าทำไมข่าวนี้สำคัญต่อการตัดสินใจ"}
  ]
}"""

_client = None


def _bedrock_client():
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("bedrock-runtime")
    return _client


def _pricing(model_id: str) -> tuple[float, float]:
    for prefix, price in MODEL_PRICING.items():
        if model_id.startswith(prefix):
            return price
    return MODEL_PRICING["amazon.nova-lite"]


def calculate_cost(input_tokens: int, output_tokens: int, model_id: str | None = None) -> dict:
    model = model_id or MODEL_ID
    input_price, output_price = _pricing(model)
    usd = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "usd": round(usd, 8),
        "thb": round(usd * USD_TO_THB, 6),
        "rate": USD_TO_THB,
        "model_id": model,
    }


def _format_number(value, digits: int = 2) -> str:
    if value is None:
        return "ไม่มีข้อมูล"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "ไม่มีข้อมูล"


def _persona_focus(persona: str) -> str:
    if persona == "dividend":
        return (
            "โฟกัส: ความมั่นคงของธุรกิจและกระแสเงินสด, ระดับเงินปันผลโดยประมาณ, "
            "แนวรับที่ปลอดภัย, เหมาะถือระยะกลาง-ยาว, หลีกเลี่ยงหุ้นผันผวนสูง"
        )
    return (
        "โฟกัส: จังหวะเทคนิค (SMA/RSI/ปริมาณซื้อขาย), โมเมนตัมและกระแสข่าวเร่งราคา, "
        "จุดเข้าทำกำไรระยะสั้น, ต้องมี Stop Loss ชัดเจน, ยอมรับความผันผวนได้"
    )


def _age_suffix(item: dict) -> str:
    """ต่อท้ายชื่อแหล่งข่าวด้วยอายุข่าว เพื่อให้ AI ให้นำหนักความใหม่ได้"""
    raw = str((item or {}).get("published_at") or "").strip()
    if not raw:
        return ""
    try:
        published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
    if hours < 0:
        return ""
    if hours < 1:
        return ", ไม่ถึง 1 ชม.ก่อน"
    if hours < 24:
        return f", {int(hours)} ชม.ก่อน"
    return f", {int(hours // 24)} วันก่อน"


def build_prompt(market: dict, persona: str) -> str:
    indicators = market.get("indicators", {})
    news = market.get("news", [])
    news_lines = (
        "\n".join(
            f"- [{index}] {item.get('title')} ({item.get('source')}{_age_suffix(item)})"
            for index, item in enumerate(news, start=1)
        )
        if news
        else "- ไม่พบข่าวล่าสุด"
    )
    currency = market.get("currency", "THB")

    return f"""วิเคราะห์หุ้นต่อไปนี้ให้ลูกค้ารายย่อยไทย แล้วตอบเป็น JSON ตามโครงสร้างที่กำหนดเท่านั้น

ข้อมูลหุ้น:
- รหัส: {market.get('symbol')}
- ชื่อ: {market.get('name')}
- ตลาด: {market.get('market')} (สกุลเงิน {currency})
- ราคาล่าสุด: {_format_number(indicators.get('price'))} {currency}
- เปลี่ยนแปลงรายวัน: {_format_number(indicators.get('change_pct'))}%
- SMA20: {_format_number(indicators.get('sma20'))} | SMA50: {_format_number(indicators.get('sma50'))}
- RSI(14): {_format_number(indicators.get('rsi14'))}
- Bias เทียบ SMA20: {_format_number(indicators.get('bias20_pct'))}%
- ปริมาณซื้อขายเทียบค่าเฉลี่ย 10 วัน: {_format_number(indicators.get('volume_ratio'))} เท่า
- 52-Week High: {_format_number(indicators.get('high_52w'))} (ห่างจากราคาปัจจุบัน {_format_number(indicators.get('dist_high_52w_pct'))}%)
- 52-Week Low: {_format_number(indicators.get('low_52w'))} (ห่างจากราคาปัจจุบัน {_format_number(indicators.get('dist_low_52w_pct'))}%)

ข่าวล่าสุด:
{news_lines}

สไตล์นักลงทุนของผู้ใช้: {persona}
{_persona_focus(persona)}

โครงสร้าง JSON ที่ต้องตอบ (ห้ามใส่ markdown หรือคำอธิบายนอก JSON):
{_RESPONSE_SCHEMA}

กฎเพิ่มเติม: ตัวเลขใน action_plan ต้องอ้างอิงจากราคาและอินดิเคเตอร์ข้างต้นเท่านั้น
ใน news_picks ให้เลือกข่าวที่สำคัญต่อการตัดสินใจจริง 1-3 ข่าวจากรายการข่าวด้านบนเท่านั้น
โดยต้องคัดลอก title ให้ตรงกับรายการ ห้ามแต่งหัวข้อใหม่ และให้เหตุผลว่าข่าวนั้นมีผลต่อราคาหรือความเสี่ยงอย่างไร
ถ้าไม่มีข่าวที่เกี่ยวข้องจริง ให้ส่ง news_picks เป็น []
ข้อความทั้งหมดต้องเป็นภาษาไทย กระชับ อ่านง่าย และต้องเป็น JSON ที่ parse ได้จริง"""


def _extract_json(text: str) -> dict:
    """ดึง JSON ก้อนแรกออกจากข้อความตอบกลับของโมเดลอย่างอดทน."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("ไม่พบ JSON ในข้อความตอบกลับ")

    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("รูปแบบ JSON ที่ได้ไม่ถูกต้อง")
    return payload


def _as_text_list(value, limit: int = 3) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = [str(item).strip() for item in value if str(item).strip()]
    return items[:limit]


def _normalize_news_picks(raw, news: list[dict], limit: int = 3) -> list[dict]:
    """รับข่าวที่ AI เลือก แต่ยอมรับเฉพาะหัวข้อที่อยู่ในรายการจริง (กันการแต่งข่าวขึ้นมาเอง)"""
    entries = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    by_title = {
        str(item.get("title") or "").strip().lower(): item
        for item in news
        if str(item.get("title") or "").strip()
    }

    picks: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            title, why = entry, ""
        elif isinstance(entry, dict):
            title = str(entry.get("title") or "")
            why = str(entry.get("why") or "")
        else:
            continue

        title = title.strip().strip('"').strip()
        if not title:
            continue

        match = by_title.get(title.lower())
        if match is None:  # ลองจับจากพาดหัวขึ้นต้นเหมือนกัน
            prefix = title.lower()[:60]
            for known, item in by_title.items():
                if known.startswith(prefix) or prefix.startswith(known[:60]):
                    match = item
                    break
        if match is None:
            continue

        key = str(match.get("title")).lower()
        if key in seen:
            continue
        seen.add(key)
        picks.append(
            {
                "title": str(match.get("title")),
                "source": str(match.get("source") or ""),
                "url": str(match.get("url") or ""),
                "why": " ".join(why.split())[:200],
            }
        )
        if len(picks) >= limit:
            break

    if not picks:  # AI ไม่เลือกหรือเลือกไม่ตรงรายการ -> ใช้ลำดับที่ดีที่สุดจากตัวกรอง
        picks = [
            {
                "title": str(item.get("title")),
                "source": str(item.get("source") or ""),
                "url": str(item.get("url") or ""),
                "why": "",
            }
            for item in news[:limit]
            if str(item.get("title") or "").strip()
        ]
    return picks


def _normalize_ai(payload: dict, persona: str, market: dict | None = None) -> dict:
    try:
        score = int(round(float(payload.get("score", 50))))
    except (TypeError, ValueError):
        score = 50
    score = max(0, min(100, score))

    signal = str(payload.get("signal", "")).strip().upper()
    if signal not in VALID_SIGNALS:
        signal = "BUY" if score >= 65 else "WATCH" if score >= 45 else "SELL"

    news_tone = _normalize_news_tone(payload.get("news_tone"), score)

    plan = payload.get("action_plan") if isinstance(payload.get("action_plan"), dict) else {}
    summary = str(payload.get("trend_summary") or "").strip()
    if not summary:
        summary = "โมเดลไม่ได้ให้บทสรุปแนวโน้มไว้"

    checklist = _as_text_list(plan.get("checklist"), 3)
    if not checklist:
        checklist = ["ติดตามราคาที่จุดเข้าซื้อ", "ตั้งจุดตัดขาดทุนก่อนซื้อ", "ติดตามข่าวสารล่าสุด"]

    return {
        "score": score,
        "signal": signal,
        "news_tone": news_tone,
        "trend_summary": summary,
        "action_plan": {
            "entry_zone": str(plan.get("entry_zone") or "รอความชัดเจนของแนวโน้มก่อน").strip(),
            "stop_loss": str(plan.get("stop_loss") or "กำหนดจุดตัดขาดทุน 5-7% จากราคาซื้อ").strip(),
            "take_profit": str(plan.get("take_profit") or "ทยอยขายทำกำไรเป็นช่วง").strip(),
            "checklist": checklist,
        },
        "catalysts": _as_text_list(payload.get("catalysts"), 3) or ["ยังไม่มีปัจจัยบวกที่ชัดเจน"],
        "risks": _as_text_list(payload.get("risks"), 3) or ["ความผันผวนของตลาดโดยรวม"],
        "news_picks": _normalize_news_picks(payload.get("news_picks"), (market or {}).get("news") or []),
        "persona": persona,
    }


def rule_based_analysis(market: dict, persona: str, reason: str = "") -> dict:
    """Fallback: สรุปผลจากกฎทางเทคนิคล้วน เมื่อเรียก Bedrock ไม่ได้
    เพื่อไม่ให้แอปพลิเคชันล่มระหว่างการนำเสนอ"""
    indicators = market.get("indicators", {})
    price = indicators.get("price") or 0.0
    sma20 = indicators.get("sma20")
    sma50 = indicators.get("sma50")
    rsi = indicators.get("rsi14")
    bias = indicators.get("bias20_pct")
    dist_high = indicators.get("dist_high_52w_pct")
    volume_ratio = indicators.get("volume_ratio")

    score = 50.0
    notes: list[str] = []
    if sma20:
        if price > sma20:
            score += 8
            notes.append("ราคายืนเหนือเส้น SMA20")
        else:
            score -= 8
            notes.append("ราคาอยู่ใต้เส้น SMA20")
    if sma50:
        if price > sma50:
            score += 7
            notes.append("ราคายังอยู่เหนือเส้น SMA50")
        else:
            score -= 7
            notes.append("ราคาหลุดเส้น SMA50")
    if rsi is not None:
        if rsi < 30:
            score += 10
            notes.append(f"RSI {rsi:,.1f} อยู่ในโซนขายมากเกินไป (Oversold)")
        elif rsi > 70:
            score -= 10
            notes.append(f"RSI {rsi:,.1f} อยู่ในโซนซื้อมากเกินไป (Overbought)")
    if bias is not None and abs(bias) > 10:
        score -= min(abs(bias) * 0.3, 6)
        notes.append(f"ราคาเบี่ยงจาก SMA20 ถึง {bias:,.1f}%")
    if dist_high is not None and dist_high > -5:
        score += 5
        notes.append("ราคาใกล้ระดับสูงสุดรอบ 52 สัปดาห์")
    if volume_ratio is not None and volume_ratio > 1.5:
        score += 3
        notes.append(f"ปริมาณซื้อขายหนุนที่ {volume_ratio:,.1f} เท่าของค่าเฉลี่ย")

    score = int(max(0, min(100, round(score))))
    signal = "BUY" if score >= 65 else "WATCH" if score >= 45 else "SELL"

    currency = market.get("currency", "THB")
    unit = "บาท" if currency == "THB" else "ดอลลาร์"
    stop_pct = 0.06 if persona == "dividend" else 0.04
    target_pct = 0.10 if persona == "dividend" else 0.07
    reason_text = f" ({reason})" if reason else ""

    return {
        "score": score,
        "signal": signal,
        "news_tone": "บวก" if score >= 65 else "ลบ" if score < 45 else "กลาง",
        "trend_summary": (
            f"สรุปจากกฎเทคนิคอัตโนมัติ{reason_text}: " + " และ".join(notes[:3])
            if notes
            else f"ข้อมูลยังไม่พอสำหรับสรุปแนวโน้มของ {market.get('symbol')}"
        ),
        "action_plan": {
            "entry_zone": (
                f"{price * 0.97:,.2f} - {price:,.2f} {unit}" if price else "รอความชัดเจนของแนวโน้ม"
            ),
            "stop_loss": f"{price * (1 - stop_pct):,.2f} {unit} (-{stop_pct * 100:.0f}%)" if price else "กำหนดเองตามความเสี่ยงที่รับได้",
            "take_profit": f"{price * (1 + target_pct):,.2f} {unit} (+{target_pct * 100:.0f}%)" if price else "ทยอยขายทำกำไรเป็นช่วง",
            "checklist": [
                "ตรวจสอบปริมาณซื้อขายก่อนเข้าซื้อจริง",
                "ตั้งจุดตัดขาดทุนให้ชัดเจนก่อนเปิดสถานะ",
                "ติดตามข่าวและผลประกอบการล่าสุดอีกครั้ง",
            ],
        },
        "catalysts": notes[:3] or ["ยังไม่มีปัจจัยบวกที่ชัดเจนจากข้อมูลเชิงเทคนิค"],
        "risks": [
            "ผลวิเคราะห์นี้มาจากกฎเทคนิคล้วน ยังไม่ได้ผ่าน AI",
            "ความผันผวนของตลาดและปัจจัยมหภาคอาจเปลี่ยนทิศทางราคา",
            "ควรตรวจสอบข้อมูลพื้นฐานและข่าวล่าสุดประกอบก่อนตัดสินใจ",
        ][:3],
        "news_picks": [
            {
                "title": str(item.get("title")),
                "source": str(item.get("source") or ""),
                "url": str(item.get("url") or ""),
                "why": "คัดจากความใหม่และความเกี่ยวข้องอัตโนมัติ (ยังไม่ได้ผ่าน AI)",
            }
            for item in (market.get("news") or [])[:3]
            if str(item.get("title") or "").strip()
        ],
        "persona": persona,
    }


def _normalize_news_tone(raw, score: int) -> str:
    """แปลงอารมณ์ข่าวให้เป็นภาษาไทยมาตรฐาน 3 ค่า: บวก / กลาง / ลบ"""
    text = str(raw or "").strip()
    if not text:
        return "บวก" if score >= 65 else "ลบ" if score < 45 else "กลาง"
    upper = text.upper()
    if "บวก" in text or "POSITIVE" in upper:
        return "บวก"
    if "ลบ" in text or "NEGATIVE" in upper:
        return "ลบ"
    return "กลาง"


def _assess_risk(market: dict, ai: dict) -> tuple[str, list[str]]:
    """ประเมินระดับความเสี่ยงจากตัวเลขจริง (ไม่ใช้ token ของ AI)
    LOW / MEDIUM / HIGH พร้อมเหตุผลสั้นๆ ไว้โชว์บนการ์ด
    """
    indicators = market.get("indicators") or {}
    volatility = indicators.get("volatility_20d_pct")
    rsi = indicators.get("rsi14")
    bias = indicators.get("bias20_pct")
    score = int(ai.get("score") or 50)
    signal = str(ai.get("signal") or "WATCH")

    reasons: list[str] = []
    high = False
    if volatility is not None and float(volatility) >= 3.0:
        high = True
        reasons.append(f"ความผันผวน 20 วันสูง ({float(volatility):.1f}%/วัน)")
    if rsi is not None and (float(rsi) >= 75 or float(rsi) <= 25):
        high = True
        reasons.append(f"RSI อยู่ที่ {float(rsi):.0f} (โซนสุดโต่ง)")
    if bias is not None and abs(float(bias)) >= 12:
        high = True
        reasons.append(f"ราคาเบี่ยงจาก SMA20 {float(bias):.0f}%")
    if score < 45 or signal == "SELL":
        high = True
        reasons.append("คะแนนและสัญญาณยังอยู่ในเกณฑ์ลบ")

    if high:
        return "HIGH", reasons[:3]

    low = (
        volatility is not None
        and float(volatility) < 1.5
        and score >= 60
        and rsi is not None
        and 40 <= float(rsi) <= 65
    )
    if low:
        return "LOW", ["ความผันผวนต่ำและสัญญาณเชิงบวกสอดคล้องกัน"]
    return "MEDIUM", reasons[:3] or ["ความเสี่ยงระดับปกติของหุ้นรายตัว"]


def _invoke_bedrock(prompt: str, persona: str) -> tuple[str, dict]:
    client = _bedrock_client()
    response = client.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPTS[persona]}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={
            "maxTokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.3,
            "topP": 0.9,
        },
    )
    text_parts: list[str] = []
    message = (response.get("output") or {}).get("message") or {}
    for block in message.get("content") or []:
        if isinstance(block, dict) and "text" in block:
            text_parts.append(str(block["text"]))
    usage = response.get("usage") or {}
    input_tokens = int(usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("outputTokens") or 0)
    return "".join(text_parts), {"input": input_tokens, "output": output_tokens}


def analyze_stock(market: dict, persona: str = "dividend") -> dict:
    """วิเคราะห์หุ้น 1 ตัว คืนผลลัพธ์ AI + ต้นทุน token (มี fallback ถ้า Bedrock ใช้ไม่ได้)."""
    persona = persona if persona in VALID_PERSONAS else "dividend"
    prompt = build_prompt(market, persona)

    try:
        text, tokens = _invoke_bedrock(prompt, persona)
        payload = _extract_json(text)
        ai = _normalize_ai(payload, persona, market)
        ai["risk_level"], ai["risk_reasons"] = _assess_risk(market, ai)
        return {
            "ai": ai,
            "source": "bedrock",
            "model_id": MODEL_ID,
            "cost": calculate_cost(tokens["input"], tokens["output"]),
            "note": "",
            "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    except Exception as exc:  # noqa: BLE001 - ต้องไม่ทำให้ทั้งพอร์ตล้ม
        short_reason = _short_error(exc)
        ai = rule_based_analysis(market, persona, short_reason)
        ai["risk_level"], ai["risk_reasons"] = _assess_risk(market, ai)
        return {
            "ai": ai,
            "source": "rule_fallback",
            "model_id": MODEL_ID,
            "cost": calculate_cost(0, 0),
            "note": f"Bedrock ใช้งานไม่ได้ในขณะนี้ ({short_reason}) ระบบจึงสรุปด้วยกฎเทคนิคให้ก่อน",
            "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


def _short_error(exc: Exception) -> str:
    name = exc.__class__.__name__
    text = str(exc).strip().replace("\n", " ")
    if "AccessDenied" in text or "not authorized" in text.lower():
        return "บัญชีนี้ยังไม่ได้รับสิทธิ์ใช้งานโมเดล"
    if "Throttl" in text:
        return "ถูกจำกัดจำนวนการเรียกใช้ชั่วคราว"
    if "ValidationException" in text:
        return "โมเดลไม่รองรับคำขอนี้"
    if "EndpointConnectionError" in text or "ConnectTimeout" in text:
        return "เชื่อมต่อบริการ Bedrock ไม่ได้"
    return f"{name}: {text[:120]}" if text else name
