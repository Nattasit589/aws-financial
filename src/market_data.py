"""market_data.py — ดึงราคาหุ้นด้วย yfinance, คำนวณอินดิเคเตอร์พื้นฐาน และดึงข่าวล่าสุด

หลักการออกแบบ:
- ไม่ import pandas เองในโค้ด (yfinance คืน DataFrame มาให้แล้วเราแปลงเป็น list ทีละแท่ง)
  เพื่อลดขนาดแพ็กเกจและลดความเสี่ยงเวลา build บน AWS Lambda
- ทุกข้อผิดพลาดที่ผู้ใช้แก้เองได้จะถูกโยนเป็น MarketDataError พร้อมข้อความภาษาไทย
  เพื่อให้หน้าเว็บแสดงผลได้สวยงามแทนการเกิด 500 Internal Server Error
"""

from __future__ import annotations

import math
import re
import statistics
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.^=-]{1,15}$")
NEWS_LIMIT = 5
NEWS_TIMEOUT_SECONDS = 6
USER_AGENT = "Mozilla/5.0 (compatible; AIEquityCoPilot/1.0; +https://aws.amazon.com/lambda/)"


class MarketDataError(Exception):
    """ข้อผิดพลาดที่ผู้ใช้แก้ไขเองได้ (พิมพ์รหัสหุ้นผิด / ดึงข้อมูลไม่ได้)"""


def normalize_symbol(raw: str) -> str:
    """แปลงรหัสหุ้นที่ผู้ใช้พิมพ์ให้เป็นรูปแบบมาตรฐาน เช่น ' ptt.bk ' -> 'PTT.BK'."""
    symbol = (raw or "").strip().upper().replace(" ", "")
    if not symbol:
        raise MarketDataError("กรุณาพิมพ์รหัสหุ้นก่อนกดเพิ่ม")
    if not SYMBOL_PATTERN.match(symbol):
        raise MarketDataError(
            f"รหัสหุ้น '{raw}' ไม่ถูกต้อง (ตัวอย่างที่ใช้ได้: PTT.BK, ADVANC.BK, NVDA, AAPL)"
        )
    return symbol


def is_thai_symbol(symbol: str) -> bool:
    return symbol.endswith(".BK")


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """RSI แบบค่าเฉลี่ยอย่างง่าย (Simple Average) ของกำไร/ขาดทุน period วันล่าสุด."""
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for index in range(len(closes) - period, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _history_rows(symbol: str):
    """คืน (ticker, rows, metadata) โดย rows เป็น list ของแท่งราคารายวัน เรียงจากเก่าไปใหม่

    metadata มาจาก ``history_metadata`` ของ yfinance ซึ่งได้มาฟรีจาก response เดียวกัน
    (shortName / longName / currency / exchangeName) จึงไม่ต้องเรียก ``ticker.info``
    ที่ช้ากว่าและถูก Yahoo จำกัดอัตราการเรียกบ่อยกว่า
    """
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover - ขึ้นกับสภาพแวดล้อม Lambda
        raise MarketDataError("ระบบโหลดไลบรารีราคาหุ้นไม่สำเร็จ กรุณาลองใหม่อีกครั้ง") from exc

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="1y", auto_adjust=True)
    except Exception as exc:
        raise MarketDataError(
            f"เชื่อมต่อแหล่งข้อมูลราคาของ {symbol} ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"
        ) from exc

    if history is None or len(history) == 0:
        raise MarketDataError(f"ไม่พบข้อมูลราคาของ {symbol} กรุณาตรวจสอบรหัสหุ้นอีกครั้ง")

    rows: list[dict[str, float]] = []
    for row in history.itertuples(index=False):
        close = _number(getattr(row, "Close", None))
        if close is None or close <= 0:
            continue
        volume = _number(getattr(row, "Volume", None)) or 0.0
        high = _number(getattr(row, "High", None)) or close
        low = _number(getattr(row, "Low", None)) or close
        rows.append({"close": close, "high": high, "low": low, "volume": volume})

    if len(rows) < 2:
        raise MarketDataError(f"ข้อมูลราคาของ {symbol} มีไม่เพียงพอต่อการวิเคราะห์")

    try:
        metadata = dict(getattr(ticker, "history_metadata", None) or {})
    except Exception:  # pragma: no cover - metadata เป็นข้อมูลเสริม
        metadata = {}

    return ticker, rows, metadata


def build_indicators(rows: list[dict[str, float]]) -> dict[str, float | None]:
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]

    price = closes[-1]
    previous_close = closes[-2]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    rsi14 = _rsi(closes)
    high_52w = max(highs)
    low_52w = min(lows)

    previous_volumes = volumes[-11:-1]
    average_volume_10 = sum(previous_volumes) / len(previous_volumes) if previous_volumes else None
    volume_ratio = None
    if average_volume_10 and average_volume_10 > 0:
        volume_ratio = volumes[-1] / average_volume_10

    bias20 = None
    if sma20:
        bias20 = (price / sma20 - 1.0) * 100.0

    dist_high52 = (price / high_52w - 1.0) * 100.0 if high_52w else None
    dist_low52 = (price / low_52w - 1.0) * 100.0 if low_52w else None

    # ความผันผวนจริง 20 วัน (ส่วนเบี่ยงเบนมาตรฐานของผลตอบแทนรายวัน) ใช้ประเมินระดับความเสี่ยง
    volatility_20d = None
    if len(closes) >= 21:
        returns = [
            (closes[index] / closes[index - 1] - 1.0) * 100.0
            for index in range(len(closes) - 20, len(closes))
        ]
        volatility_20d = statistics.pstdev(returns)

    return {
        "price": _round(price),
        "prev_close": _round(previous_close),
        "change_pct": _round((price / previous_close - 1.0) * 100.0),
        "sma20": _round(sma20),
        "sma50": _round(sma50),
        "rsi14": _round(rsi14),
        "bias20_pct": _round(bias20),
        "volume_ratio": _round(volume_ratio),
        "high_52w": _round(high_52w),
        "low_52w": _round(low_52w),
        "dist_high_52w_pct": _round(dist_high52),
        "dist_low_52w_pct": _round(dist_low52),
        "volatility_20d_pct": _round(volatility_20d),
    }


def _company_name(metadata: dict, symbol: str) -> str:
    """ตั้งชื่อบริษัทจาก metadata ของ history โดยไม่ต้องยิง request เพิ่ม

    Yahoo ตั้ง shortName ของหุ้นไทยเป็น ``ADVANC_ADVANCED INFO SERVICE`` (รหัสนำหน้าชื่อจีน)
    จึงตัดส่วนนำหน้าที่ซ้ำกับรหัสหุ้นออกก่อน
    """
    short = str(metadata.get("shortName") or "").strip()
    long_name = str(metadata.get("longName") or "").strip()
    base = symbol.split(".")[0]

    if "_" in short:
        prefix, _, rest = short.partition("_")
        rest = rest.replace("_", " ").strip()
        if prefix.upper() == base:
            if rest and rest.upper() != base:
                return rest
            if long_name:
                return long_name

    for candidate in (short, long_name):
        name = candidate.replace("_", " ").strip()
        if name:
            return name
    return symbol


def _yfinance_news(ticker) -> list[dict[str, str]]:
    if ticker is None:
        return []
    try:
        raw_items = getattr(ticker, "news", None) or []
    except Exception:
        return []

    headlines: list[dict[str, str]] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content") if isinstance(entry.get("content"), dict) else entry
        title = str(content.get("title") or entry.get("title") or "").strip()
        if not title:
            continue

        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else None
        canonical = content.get("canonicalUrl")
        url = canonical.get("url") if isinstance(canonical, dict) else None

        headlines.append(
            {
                "title": title,
                "source": str(publisher or entry.get("publisher") or "Yahoo Finance"),
                "url": str(url or entry.get("link") or ""),
                "origin": "yfinance",
            }
        )
        if len(headlines) >= NEWS_LIMIT:
            break
    return headlines


def _google_news(symbol: str) -> list[dict[str, str]]:
    """ดึงหัวข้อข่าวล่าสุดจาก Google News RSS ด้วยไลบรารีมาตรฐานของ Python เท่านั้น."""
    base = symbol[:-3] if is_thai_symbol(symbol) else symbol
    if is_thai_symbol(symbol):
        query = f"{base} หุ้น"
        locale = "hl=th&gl=TH&ceid=TH:th"
    else:
        query = f"{base} stock"
        locale = "hl=en-US&gl=US&ceid=US:en"

    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&{locale}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=NEWS_TIMEOUT_SECONDS) as response:
            payload = response.read()
        root = ET.fromstring(payload)
    except Exception:
        # ข่าวเป็นข้อมูลเสริม ถ้าดึงไม่ได้ก็ปล่อยผ่าน ไม่ทำให้การวิเคราะห์ล้มทั้งรอบ
        return []

    headlines: list[dict[str, str]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        headlines.append(
            {
                "title": title,
                "source": (item.findtext("source") or "Google News").strip(),
                "url": (item.findtext("link") or "").strip(),
                "origin": "google_news",
            }
        )
        if len(headlines) >= NEWS_LIMIT:
            break
    return headlines


def _dedupe_news(items: list[dict[str, str]]) -> list[dict[str, str]]:
    combined = list(items)
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in combined:
        key = item["title"].lower()[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:NEWS_LIMIT]


def fetch_news(symbol: str, ticker=None) -> list[dict[str, str]]:
    return _dedupe_news(_yfinance_news(ticker) + _google_news(symbol))


def fetch_market_data(symbol: str) -> dict:
    """ดึงข้อมูลครบชุดของหุ้น 1 ตัว พร้อมข้อมูลพร้อมใช้สำหรับส่งให้ AI.

    ลำดับการทำงานถูกจัดให้รอ network น้อยที่สุด:
    1. ยิง Google News RSS ไปก่อน (เป็น call ที่ช้าที่สุด ~0.5 วินาที) ใน thread แยก
    2. ระหว่างรอ ดึงราคา + ข่าว yfinance ใน thread หลัก
    3. รวมข่าวทั้งสองแหล่งแล้วคืนผล
    """
    started = time.perf_counter()
    symbol = normalize_symbol(symbol)
    thai = is_thai_symbol(symbol)

    with ThreadPoolExecutor(max_workers=2) as executor:
        rss_future = executor.submit(_google_news, symbol)
        ticker, rows, metadata = _history_rows(symbol)
        yf_news = _yfinance_news(ticker)
        rss_news = rss_future.result()

    indicators = build_indicators(rows)
    currency = str(metadata.get("currency") or ("THB" if thai else "USD"))
    exchange = str(metadata.get("fullExchangeName") or metadata.get("exchangeName") or "").strip()

    if thai:
        market = "ตลาดหลักทรัพย์แห่งประเทศไทย (SET)"
    else:
        market = f"ตลาดหุ้นสหรัฐฯ ({exchange})" if exchange else "ตลาดหุ้นสหรัฐฯ"

    return {
        "symbol": symbol,
        "name": _company_name(metadata, symbol),
        "currency": currency,
        "market": market,
        "indicators": indicators,
        "news": _dedupe_news(yf_news + rss_news),
        "data_points": len(rows),
        "fetch_ms": int((time.perf_counter() - started) * 1000),
    }
