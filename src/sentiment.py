"""sentiment.py — Greed & Fear Index (composite 0–100) ของตลาด + พอร์ตผู้ใช้

ดัชนีนี้คำนวณเองทั้งหมดจากข้อมูลที่โปรเจกต์ดึงอยู่แล้ว (yfinance + ผลวิเคราะห์ของ AI)
จึงไม่เพิ่ม AWS service ใหม่ ไม่เพิ่ม dependency และไม่มีปัญหา endpoint ภายนอกถูกบล็อก

องค์ประกอบ 7 ตัว (น้ำหนักจะถูกปรับใหม่ให้รวมเป็น 100% เมื่อข้อมูลบางตัวขาด):

| องค์ประกอบ | น้ำหนัก | ความหมาย |
|---|---|---|
| volatility  | 0.20 | VIX ต่ำ = ตลาดไม่กลัว (greed) |
| momentum    | 0.20 | ดัชนีตลาด (S&P 500 / SET) เทียบ SMA50 |
| breadth     | 0.15 | สัดส่วนหุ้นในพอร์ตที่ยืนเหนือ SMA20 |
| technical   | 0.15 | RSI14 เฉลี่ยของพอร์ต |
| positioning | 0.10 | ระยะห่างจากจุดสูงสุด 52 สัปดาห์ |
| news        | 0.10 | อารมณ์ข่าวที่ AI ประเมิน (บวก/กลาง/ลบ) |
| signals     | 0.10 | สัดส่วนสัญญาณ BUY/WATCH/SELL |

ข้อจำกัดที่ต้องบอกผู้ใช้ตรง ๆ: นี่คือ "ดัชนีของโปรเจกต์นี้" ไม่ใช่ CNN Fear & Greed
และไม่ใช่คำแนะนำการลงทุน
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

VOLATILITY_TICKER = "^VIX"
MOMENTUM_TICKERS = ("^GSPC", "^SET.BK")
HISTORY_POINTS = 30
CONTEXT_TTL_SECONDS = 900  # กันการยิง yfinance ซ้ำในรอบเดียวกัน (10-15 นาทีก็เพียงพอ)

WEIGHTS = {
    "volatility": 0.20,
    "momentum": 0.20,
    "breadth": 0.15,
    "technical": 0.15,
    "positioning": 0.10,
    "news": 0.10,
    "signals": 0.10,
}

COMPONENT_NAMES = {
    "volatility": "ความผันผวนตลาด (VIX)",
    "momentum": "โมเมนตัมดัชนีตลาด",
    "breadth": "ความกว้างของตลาดในพอร์ต",
    "technical": "ความร้อนแรงทางเทคนิค (RSI)",
    "positioning": "ตำแหน่งราคาเทียบ 52 สัปดาห์",
    "news": "อารมณ์ข่าว",
    "signals": "สัญญาณ AI ในพอร์ต",
}

# ระดับของดัชนีใช้ชื่อภาษาอังกฤษตามมาตรฐานที่นักลงทุนคุ้นเคย
BANDS = (
    (25.0, "extreme_fear", "Extreme Fear", "🥶", "negative"),
    (45.0, "fear", "Fear", "😨", "warning"),
    (55.0, "neutral", "Neutral", "😐", "neutral"),
    (75.0, "greed", "Greed", "🤑", "positive"),
    (101.0, "extreme_greed", "Extreme Greed", "🔥", "positive"),
)

# องค์ประกอบจากพอร์ตต้องมีหุ้นอย่างน้อยเท่านี้ ไม่งั้น 1 หุ้นจะลากดัชนีทั้งตลาด
MIN_PORTFOLIO_SAMPLE = 3

NEWS_SCORES = {"บวก": 88.0, "กลาง": 50.0, "ลบ": 12.0}
SIGNAL_SCORES = {"BUY": 100.0, "WATCH": 50.0, "SELL": 8.0}

_context: dict | None = None
_context_at: float = 0.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def band(score: float) -> dict:
    """แปลงคะแนนเป็นระดับความกลัว/โลภ 5 ขั้น"""
    for ceiling, key, label, emoji, tone in BANDS:
        if score < ceiling:
            return {"key": key, "label": label, "emoji": emoji, "tone": tone}
    return {"key": "greed", "label": "Greed", "emoji": "🤑", "tone": "positive"}


# --------------------------------------------------------------------------
# ส่วนตลาด (VIX + ดัชนีอ้างอิง) — เรียก network เฉพาะส่วนนี้ และ cache ไว้
# --------------------------------------------------------------------------
def _market_series(symbol: str, period: str = "1y") -> tuple[list[str], list[float]]:
    """ปิดรายวันของ ticker พร้อมวันที่ (ใช้ ``history`` เหมือน market_data)"""
    import yfinance as yf

    history = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if history is None or len(history) == 0:
        raise ValueError(f"no history for {symbol}")

    closes: list[float] = []
    dates: list[str] = []
    for index, value in zip(history.index.tolist(), history["Close"].tolist()):
        number = _number(value)
        if not number or number <= 0:
            continue
        closes.append(number)
        dates.append(str(index)[:10])
    if len(closes) < 55:  # ต้องพอคำนวณ SMA50
        raise ValueError(f"not enough history for {symbol}")
    return dates, closes


def _volatility_score(vix: float) -> float:
    """VIX 10 = โลภมาก, 20 = กลาง, 30+ = กลัวมาก"""
    return _clamp(100.0 - (vix - 10.0) * 4.5)


def _momentum_score(closes: list[float]) -> float | None:
    """% เหนือ SMA50 แปลงเป็น 0–100 (ต่ำกว่า 10% = 0, สูงกว่า 10% = 100)"""
    average = _sma(closes, 50)
    if not average:
        return None
    pct = (closes[-1] / average - 1.0) * 100.0
    return _clamp(50.0 + pct * 5.0)


def _market_history(
    vix_dates: list[str], vix: list[float], indices: list[list[float]]
) -> list[dict]:
    """ดัชนีย้อนหลัง 30 วันซื้อขาย จากส่วนตลาดเท่านั้น (VIX + โมเมนตัม)"""
    span = min([HISTORY_POINTS, len(vix)] + [len(series) for series in indices])
    history: list[dict] = []
    for offset in range(span, 0, -1):
        end = len(vix) - offset + 1
        if end < 2:
            continue
        scores = [_volatility_score(vix[end - 1])]
        for series in indices:
            momentum = _momentum_score(series[: len(series) - offset + 1])
            if momentum is not None:
                scores.append(momentum)
        history.append(
            {
                "date": vix_dates[end - 1],
                "score": round(sum(scores) / len(scores), 1),
            }
        )
    return history


def market_context(force: bool = False) -> dict:
    """บริบทตลาด (VIX + ดัชนี) พร้อม cache ในหน่วยความจำของ container"""
    global _context, _context_at
    if not force and _context is not None and (time.time() - _context_at) < CONTEXT_TTL_SECONDS:
        return _context

    result: dict = {
        "vix": None,
        "momentum": {},
        "history": [],
        "missing": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    series: dict[str, tuple[list[str], list[float]]] = {}
    with ThreadPoolExecutor(max_workers=1 + len(MOMENTUM_TICKERS)) as executor:
        futures = {VOLATILITY_TICKER: executor.submit(_market_series, VOLATILITY_TICKER)}
        for ticker in MOMENTUM_TICKERS:
            futures[ticker] = executor.submit(_market_series, ticker)
        for ticker, future in futures.items():
            try:
                series[ticker] = future.result()
            except Exception:  # noqa: BLE001 - ขาดแหล่งใดแหล่งหนึ่งยังคำนวณต่อได้
                result["missing"].append(ticker)

    vix_dates: list[str] = []
    vix: list[float] = []
    if VOLATILITY_TICKER in series:
        vix_dates, vix = series[VOLATILITY_TICKER]
        result["vix"] = round(vix[-1], 2)
        result["vix_average_90d"] = round(sum(vix[-90:]) / len(vix[-90:]), 2)

    indices: list[list[float]] = []
    for ticker in MOMENTUM_TICKERS:
        closes = series.get(ticker, ([], []))[1]
        if not closes:
            continue
        score = _momentum_score(closes)
        if score is None:
            continue
        average = _sma(closes, 50) or closes[-1]
        result["momentum"][ticker] = {
            "score": round(score, 1),
            "pct_vs_sma50": round((closes[-1] / average - 1.0) * 100.0, 2),
        }
        indices.append(closes)

    if vix and indices:
        result["history"] = _market_history(vix_dates, vix, indices)

    _context = result
    _context_at = time.time()
    return result


# --------------------------------------------------------------------------
# ส่วนพอร์ต (ผลวิเคราะห์ที่มีอยู่แล้ว ไม่ต้องเรียก network)
# --------------------------------------------------------------------------
def _portfolio_components(results: list[dict]) -> dict[str, dict]:
    valid = [item for item in results if item.get("ai") and not item.get("error")]
    components: dict[str, dict] = {}
    if len(valid) < MIN_PORTFOLIO_SAMPLE:  # ตัวอย่างน้อยเกินกว่าจะเป็นตัวแทนของตลาด
        return components

    above_sma20 = 0
    sma_checks = 0
    rsi_values: list[float] = []
    distances: list[float] = []
    tones: list[float] = []
    signals: list[float] = []

    for item in valid:
        indicators = item.get("indicators") or {}
        price = _number(indicators.get("price"))
        sma20 = _number(indicators.get("sma20"))
        if price is not None and sma20:
            sma_checks += 1
            above_sma20 += 1 if price >= sma20 else 0
        rsi = _number(indicators.get("rsi14"))
        if rsi is not None:
            rsi_values.append(rsi)
        distance = _number(indicators.get("dist_high_52w_pct"))
        if distance is not None:
            distances.append(distance)
        tone = str((item.get("ai") or {}).get("news_tone") or "").strip()
        if tone in NEWS_SCORES:
            tones.append(NEWS_SCORES[tone])
        signal = str((item.get("ai") or {}).get("signal") or "").upper()
        if signal in SIGNAL_SCORES:
            signals.append(SIGNAL_SCORES[signal])

    total = len(valid)

    if sma_checks:
        ratio = above_sma20 / sma_checks * 100.0
        components["breadth"] = {
            "score": _clamp(ratio),
            "detail": f"{above_sma20}/{sma_checks} หุ้นยืนเหนือ SMA20",
        }

    if rsi_values:
        average_rsi = sum(rsi_values) / len(rsi_values)
        # RSI 30 = กลัวสุด, 50 = กลาง, 70 = โลภสุด
        components["technical"] = {
            "score": _clamp((average_rsi - 30.0) / 40.0 * 100.0),
            "detail": f"RSI14 เฉลี่ย {average_rsi:.1f}",
        }

    if distances:
        average_distance = sum(distances) / len(distances)
        # ห่างจุดสูงสุด 0% = 100 คะแนน, ห่าง 30% ขึ้นไป = 0 คะแนน
        components["positioning"] = {
            "score": _clamp(100.0 + average_distance * (100.0 / 30.0)),
            "detail": f"เฉลี่ยต่ำกว่าจุดสูงสุด 52 สัปดาห์ {abs(average_distance):.1f}%",
        }

    if tones:
        components["news"] = {
            "score": _clamp(sum(tones) / len(tones)),
            "detail": f"AI ประเมินอารมณ์ข่าวแล้ว {len(tones)}/{total} หุ้น",
        }

    if signals:
        components["signals"] = {
            "score": _clamp(sum(signals) / len(signals)),
            "detail": f"จากสัญญาณ AI {len(signals)} หุ้น",
        }

    return components


def _market_components(context: dict) -> dict[str, dict]:
    components: dict[str, dict] = {}
    vix = _number(context.get("vix"))
    if vix is not None:
        average = _number(context.get("vix_average_90d"))
        detail = f"VIX {vix:.2f}"
        if average:
            detail += f" (เฉลี่ย 90 วัน {average:.2f})"
        components["volatility"] = {"score": _volatility_score(vix), "detail": detail}

    momentum = context.get("momentum") or {}
    if momentum:
        scores = [entry["score"] for entry in momentum.values()]
        parts = []
        for ticker, entry in momentum.items():
            name = {"^GSPC": "S&P 500", "^SET.BK": "SET"}.get(ticker, ticker)
            parts.append(f"{name} {entry['pct_vs_sma50']:+.1f}% เทียบ SMA50")
        components["momentum"] = {
            "score": _clamp(sum(scores) / len(scores)),
            "detail": " · ".join(parts),
        }

    return components


def _drivers(components: dict[str, dict]) -> list[str]:
    """บอก 2 ปัจจัยที่ดันดัชนีไปทางใดทางหนึ่งมากที่สุด"""
    ranked = sorted(
        components.items(),
        key=lambda entry: abs(entry[1]["score"] - 50.0),
        reverse=True,
    )
    drivers: list[str] = []
    for key, entry in ranked[:2]:
        direction = "หนุนความโลภ" if entry["score"] >= 50 else "กดดันให้กลัว"
        drivers.append(f"{COMPONENT_NAMES.get(key, key)}: {entry['detail']} ({direction})")
    return drivers


def compute(results: list[dict], context: dict | None = None) -> dict:
    """คำนวณดัชนีจากผลวิเคราะห์ของพอร์ต + บริบทตลาด (ทนต่อข้อมูลที่ขาด)"""
    context = context if context is not None else market_context()
    available: dict[str, dict] = {}
    available.update(_market_components(context))
    available.update(_portfolio_components(results))

    weighted = 0.0
    weight_sum = 0.0
    components: list[dict] = []
    for key, weight in WEIGHTS.items():
        entry = available.get(key)
        if not entry:
            continue
        score = round(_clamp(entry["score"]), 1)
        weighted += score * weight
        weight_sum += weight
        components.append(
            {
                "key": key,
                "name": COMPONENT_NAMES.get(key, key),
                "score": score,
                "weight": weight,
                "weight_pct": round(weight / sum(WEIGHTS.values()) * 100),
                "detail": entry["detail"],
            }
        )

    if not components:
        return {
            "available": False,
            "score": None,
            "band": band(50.0),
            "components": [],
            "drivers": [],
            "history": [],
            "message": "ยังไม่มีข้อมูลพอคำนวณดัชนี",
        }

    portfolio_used = any(
        component["key"] in {"breadth", "technical", "positioning", "news", "signals"}
        for component in components
    )

    score = round(weighted / weight_sum, 1)
    shares = [component["weight"] / weight_sum * 100.0 for component in components]
    rounded = [round(share) for share in shares]
    # ปรับเศษปัดให้ผลรวมเป็น 100% พอดี (ให้ตัวที่น้ำหนักมากที่สุดรับส่วนต่าง)
    if rounded:
        biggest = max(range(len(rounded)), key=lambda index: shares[index])
        rounded[biggest] += 100 - sum(rounded)
    for component, share in zip(components, rounded):  # น้ำหนักจริงหลังปรับให้ครบ 100%
        component["effective_weight_pct"] = share

    history = [
        {"date": point["date"], "score": point["score"]}
        for point in (context.get("history") or [])
    ]
    note = ""
    if not portfolio_used:
        note = (
            f"พอร์ตมีหุ้นที่วิเคราะห์สำเร็จน้อยกว่า {MIN_PORTFOLIO_SAMPLE} ตัว "
            "ดัชนีรอบนี้จึงใช้เฉพาะข้อมูลตลาด (VIX + โมเมนตัม)"
        )

    return {
        "available": True,
        "score": score,
        "note": note,
        "band": band(score),
        "components": components,
        "drivers": _drivers(available),
        "history": history,
        "coverage": {"used": len(components), "total": len(WEIGHTS)},
        "missing": context.get("missing") or [],
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "history_note": "เส้นย้อนหลังคำนวณจาก VIX + โมเมนตัมตลาด (ไม่รวมข้อมูลพอร์ต)",
        "method": "ดัชนีเชิงผสม 7 องค์ประกอบ ถ่วงน้ำหนักตามข้อมูลที่วัดได้ในรอบนั้น",
        "disclaimer": "ดัชนีนี้คำนวณโดยโปรเจกต์เอง ไม่ใช่ CNN Fear & Greed และไม่ใช่คำแนะนำการลงทุน",
    }
