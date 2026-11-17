"""Local, in-memory dashboard fixtures; never imports the deployed application."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "src" / "templates" / "index.html"
MAX_SYMBOLS = 10
MAX_BODY_BYTES = 16 * 1024
PERSONAS = ("dividend", "momentum")
BANNER = "OFFLINE PREVIEW — fixtures only; no AWS/email calls"
FIXTURE_NOTE = "OFFLINE FIXTURE — ราคา ข่าว AI และต้นทุนเป็นข้อมูลสมมติ ไม่ใช่ข้อมูลตลาดจริง"
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; frame-src 'none'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
PROFILES = {
    "PTT.BK": {
        "name": "PTT Public Company Limited", "price": 32.50, "change": 0.78,
        "sma20": 31.80, "sma50": 31.20, "rsi": 57.4, "volume": 1.12,
        "high": 36.50, "low": 28.00, "volatility": 1.1,
        "score": 76, "risk": "LOW", "source": "bedrock",
        "model": "offline-fixture-nova-lite", "usd": 0.000148,
        "trend": "ราคาสมมติอยู่เหนือเส้นค่าเฉลี่ย แนวโน้มค่อย ๆ ฟื้นตัว เหมาะทดสอบมุมมองสายปันผล",
        "headline": "PTT: ตัวอย่างข่าวสมมติเรื่องกระแสเงินสดและแผนลงทุนระยะยาว",
    },
    "NVDA": {
        "name": "NVIDIA Corporation", "price": 138.25, "change": 2.34,
        "sma20": 129.40, "sma50": 122.80, "rsi": 71.2, "volume": 1.78,
        "high": 153.00, "low": 86.00, "volatility": 3.2,
        "score": 61, "risk": "HIGH", "source": "gemini_fallback",
        "model": "offline-fixture-gemini", "usd": 0.000215,
        "trend": "โมเมนตัมสมมติเป็นบวก แต่ RSI สูงและราคาผันผวน ควรรอจังหวะย่อตัวในสถานการณ์ตัวอย่าง",
        "headline": "NVDA: ตัวอย่างข่าวสมมติเรื่องความต้องการชิป AI และความผันผวน",
    },
    "AAPL": {
        "name": "Apple Inc.", "price": 204.80, "change": -1.16,
        "sma20": 213.10, "sma50": 219.50, "rsi": 38.5, "volume": 1.24,
        "high": 239.50, "low": 164.00, "volatility": 1.9,
        "score": 39, "risk": "MEDIUM", "source": "rule_fallback",
        "model": "offline-fixture-rules", "usd": 0.0,
        "trend": "ราคาสมมติต่ำกว่าเส้นค่าเฉลี่ย แนวโน้มอ่อนตัว ใช้ทดสอบหน้าจอสัญญาณขายและกฎสำรอง",
        "headline": "AAPL: ตัวอย่างข่าวสมมติเรื่องยอดขายอุปกรณ์และต้นทุนการผลิต",
    },
}


class APIError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def normalize_workspace(raw: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]", "", raw.strip()).upper()[:32]
    if not normalized:
        raise APIError("กรุณาระบุ Workspace Code (ตัวอักษรอังกฤษ ตัวเลข - หรือ _)")
    return normalized


def normalize_symbol(raw: str) -> str:
    if not isinstance(raw, str):
        raise APIError("symbol ต้องเป็นข้อความ")
    normalized = raw.strip().upper().replace(" ", "")
    if not re.fullmatch(r"[A-Z0-9.^=-]{1,15}", normalized):
        raise APIError("รหัสหุ้นไม่ถูกต้อง (ตัวอย่าง: PTT.BK, NVDA, AAPL)")
    return normalized


def fixture(symbol: str, persona: str, timestamp: str | None = None) -> dict:
    profile = PROFILES.get(symbol, PROFILES["PTT.BK"])
    price = profile["price"]
    thai = symbol.endswith(".BK")
    currency = "THB" if thai else "USD"
    score = min(100, profile["score"] + (5 if persona == "momentum" else 0))
    news = [{
        "title": "[ข่าวสมมติ] " + (profile["headline"] if symbol in PROFILES else f"{symbol}: ตัวอย่างข่าวสำหรับทดสอบหน้าจอ"),
        "source": "Offline fixture (not a news report)", "origin": "offline_fixture",
        "url": "", "published_at": timestamp or now_iso(),
    }]
    cost_usd = profile["usd"]
    trend = 0.06 if profile["change"] >= 0 else -0.06
    spark = [round(price * (1 - trend * (29 - i) / 29 + math.sin(i * 1.2) * 0.008), 2) for i in range(30)]
    spark[-1] = price
    return {
        "symbol": symbol,
        "name": f"{profile['name'] if symbol in PROFILES else symbol} [DUMMY FIXTURE]",
        "currency": currency, "market": "SET" if thai else "NASDAQ",
        "indicators": {
            "price": price, "prev_close": round(price / (1 + profile["change"] / 100), 2),
            "change_pct": profile["change"], "sma20": profile["sma20"], "sma50": profile["sma50"],
            "rsi14": profile["rsi"], "volume_ratio": profile["volume"],
            "bias20_pct": round((price / profile["sma20"] - 1) * 100, 2),
            "high_52w": profile["high"], "low_52w": profile["low"],
            "dist_high_52w_pct": round((price / profile["high"] - 1) * 100, 2),
            "dist_low_52w_pct": round((price / profile["low"] - 1) * 100, 2),
            "volatility_20d_pct": profile["volatility"],
        },
        "spark": spark, "news": news, "data_points": 252, "fetch_ms": 0,
        "ai": {
            "score": score, "signal": "BUY" if score >= 65 else "WATCH" if score >= 45 else "SELL",
            "risk_level": profile["risk"],
            "risk_reasons": [f"ความผันผวนสมมติ {profile['volatility']}% ต่อวัน", "ระดับความเสี่ยงตัวอย่างสำหรับทดสอบ UI เท่านั้น"],
            "news_tone": "บวก" if score >= 65 else "กลาง" if score >= 45 else "ลบ",
            "trend_summary": "[ข้อมูลสมมติ] " + profile["trend"],
            "action_plan": {
                "entry_zone": f"{price * 0.97:.2f}–{price:.2f} {currency} (สมมติ)",
                "stop_loss": f"{price * 0.94:.2f} {currency} (สมมติ)",
                "take_profit": f"{price * 1.10:.2f} {currency} (สมมติ)",
                "checklist": ["ข้อมูลตัวอย่าง ไม่ใช้ส่งคำสั่งซื้อขาย", "ทดสอบการแสดงแผนและจุดตัดขาดทุน", "ไม่มีการดึงราคาหรือเรียก AI จริง"],
            },
            "catalysts": ["ตัวอย่างแนวโน้มยอดขายฟื้นตัว (สมมติ)", "ตัวอย่างแรงซื้อเพิ่มขึ้น (สมมติ)"],
            "risks": ["ตัวอย่างความผันผวนของตลาด (สมมติ)", "ไม่ใช่คำแนะนำการลงทุนหรือข่าวจริง"],
            "news_picks": [{**news[0], "why": "หัวข้อสมมติสำหรับทดสอบการแสดงข่าว ไม่มีลิงก์ภายนอก"}],
            "persona": persona,
        },
        "cost": {
            "input_tokens": 1200 if cost_usd else 0, "output_tokens": 320 if cost_usd else 0,
            "usd": cost_usd, "thb": round(cost_usd * 36, 6), "rate": 36.0, "model_id": profile["model"],
        },
        "source": profile["source"], "model_id": profile["model"],
        "analyzed_at": timestamp or now_iso(), "cache_hit": False, "note": FIXTURE_NOTE,
    }


def summary(results: list[dict]) -> dict:
    valid = [item for item in results if item.get("ai") and not item.get("error")]
    counts = {signal: 0 for signal in ("BUY", "WATCH", "SELL")}
    risks = {risk: 0 for risk in ("LOW", "MEDIUM", "HIGH")}
    for item in valid:
        counts[item["ai"]["signal"]] += 1
        risks[item["ai"]["risk_level"]] += 1
    average = round(sum(item["ai"]["score"] for item in valid) / len(valid), 1) if valid else 0.0
    usd = sum(item["cost"]["usd"] for item in valid)
    verdict = "แนวโน้มตัวอย่างเป็นบวก" if average >= 65 else "แนวโน้มตัวอย่างเป็นกลาง" if average >= 45 else "แนวโน้มตัวอย่างมีความเสี่ยงสูง"
    return {
        "avg_score": average, "counts": counts, "risk_counts": risks, "analyzed_count": len(valid),
        "total_cost_usd": round(usd, 6), "total_cost_thb": round(usd * 36, 4),
        "verdict": f"[OFFLINE FIXTURE] {verdict} — ไม่ใช่คำแนะนำการลงทุน" if valid else "[OFFLINE FIXTURE] ยังไม่มีผลวิเคราะห์ที่สำเร็จ",
        "highlights": [
            {"symbol": item["symbol"], "score": item["ai"]["score"], "signal": item["ai"]["signal"]}
            for item in sorted(valid, key=lambda item: item["ai"]["score"], reverse=True)[:3]
        ],
    }


def sentiment_fixture(results: list[dict]) -> dict | None:
    """ข้อมูล Greed & Fear Index จำลอง (ไม่เรียก network) ให้หน้าพรีวิวเหมือน API จริง"""
    valid = [item for item in results if item.get("ai") and not item.get("error")]
    if not valid:
        return None
    above = sum(1 for item in valid if item["indicators"]["price"] >= (item["indicators"].get("sma20") or 0))
    rsi = sum(item["indicators"].get("rsi14") or 50 for item in valid) / len(valid)
    components = [
        {"key": "volatility", "name": "ความผันผวนตลาด (VIX)", "score": 62.0, "weight": 0.20, "weight_pct": 20, "effective_weight_pct": 20, "detail": "VIX 17.40 (เฉลี่ย 90 วัน 18.10)"},
        {"key": "momentum", "name": "โมเมนตัมดัชนีตลาด", "score": 56.0, "weight": 0.20, "weight_pct": 20, "effective_weight_pct": 20, "detail": "S&P 500 +1.2% เทียบ SMA50 · SET -0.4% เทียบ SMA50"},
        {"key": "breadth", "name": "ความกว้างของตลาดในพอร์ต", "score": round(above / len(valid) * 100, 1), "weight": 0.15, "weight_pct": 15, "effective_weight_pct": 15, "detail": f"{above}/{len(valid)} หุ้นยืนเหนือ SMA20"},
        {"key": "technical", "name": "ความร้อนแรงทางเทคนิค (RSI)", "score": round(max(0, min(100, (rsi - 30) / 40 * 100)), 1), "weight": 0.15, "weight_pct": 15, "effective_weight_pct": 15, "detail": f"RSI14 เฉลี่ย {rsi:.1f}"},
        {"key": "positioning", "name": "ตำแหน่งราคาเทียบ 52 สัปดาห์", "score": 54.0, "weight": 0.10, "weight_pct": 10, "effective_weight_pct": 10, "detail": "เฉลี่ยต่ำกว่าจุดสูงสุด 52 สัปดาห์ 13.8%"},
        {"key": "news", "name": "อารมณ์ข่าว", "score": 60.0, "weight": 0.10, "weight_pct": 10, "effective_weight_pct": 10, "detail": f"AI ประเมินอารมณ์ข่าวแล้ว {len(valid)}/{len(valid)} หุ้น"},
        {"key": "signals", "name": "สัญญาณ AI ในพอร์ต", "score": 58.0, "weight": 0.10, "weight_pct": 10, "effective_weight_pct": 10, "detail": f"จากสัญญาณ AI {len(valid)} หุ้น"},
    ]
    total = sum(component["score"] * component["weight"] for component in components)
    score_value = round(total / sum(component["weight"] for component in components), 1)
    bands = ((25, "extreme_fear", "Extreme Fear", "🥶"), (45, "fear", "Fear", "😨"),
             (55, "neutral", "Neutral", "😐"), (75, "greed", "Greed", "🤑"),
             (101, "extreme_greed", "Extreme Greed", "🔥"))
    for ceiling, key, label, emoji in bands:
        if score_value < ceiling:
            band = {"key": key, "label": label, "emoji": emoji}
            break
    history = [{"date": f"2026-10-{day:02d}", "score": round(score_value - 8 + (day % 7) * 2.4, 1)} for day in range(18, 32)] + \
              [{"date": f"2026-11-{day:02d}", "score": round(score_value - 4 + (day % 9) * 1.1, 1)} for day in range(1, 17)]
    return {
        "available": True, "score": score_value, "band": band, "components": components,
        "drivers": [f"{components[0]['name']}: {components[0]['detail']} (หนุนความโลภ)",
                    f"{components[1]['name']}: {components[1]['detail']} (หนุนความโลภ)"],
        "history": history, "coverage": {"used": len(components), "total": 7}, "missing": [],
        "as_of": now_iso(), "history_note": "เส้นย้อนหลังคำนวณจาก VIX + โมเมนตัมตลาด (ข้อมูลตัวอย่าง)",
        "method": "[OFFLINE FIXTURE] ดัชนีเชิงผสม 7 องค์ประกอบ ถ่วงน้ำหนักตามข้อมูลที่วัดได้",
        "disclaimer": "ดัชนีนี้คำนวณโดยโปรเจกต์เอง ไม่ใช่ CNN Fear & Greed และไม่ใช่คำแนะนำการลงทุน",
    }


class PreviewState:
    def __init__(self):
        self.lock = threading.Lock()
        self.workspaces = {}
        self.cache = {}
        seeded_at = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
        demo = self.workspace("DEMO-PORT")
        demo["symbols"] = list(PROFILES)
        demo["updated_at"] = seeded_at
        for symbol in demo["symbols"]:
            self.cache[("DEMO-PORT", symbol, "dividend")] = fixture(symbol, "dividend", seeded_at)

    def workspace(self, workspace_id: str) -> dict:
        return self.workspaces.setdefault(workspace_id, {
            "workspace_id": workspace_id, "symbols": [], "persona": "dividend", "updated_at": "",
        })

    def results(self, workspace: dict, force: bool = False, cached_only: bool = False) -> list[dict]:
        results = []
        for symbol in workspace["symbols"]:
            key = (workspace["workspace_id"], symbol, workspace["persona"])
            if not force and key in self.cache:
                results.append({**deepcopy(self.cache[key]), "cache_hit": True})
            elif cached_only:
                continue
            elif symbol == "BAD":
                results.append({"symbol": symbol, "error": "[OFFLINE FIXTURE] จำลองข้อผิดพลาด: ไม่พบข้อมูลราคาสำหรับ BAD"})
            else:
                result = fixture(symbol, workspace["persona"])
                self.cache[key] = deepcopy(result)
                results.append(result)
        return results

    def dispatch(self, method: str, path: str, body: dict) -> dict:
        match = re.fullmatch(r"/api/workspace/([^/]+)(?:/(stocks|persona|analyze|notify)(?:/([^/]+))?)?", path)
        if not match:
            raise APIError("Not found", 404)
        raw_id, action, raw_symbol = match.groups()
        expected_method = "GET" if not action else "DELETE" if action == "stocks" and raw_symbol else "POST"
        if raw_symbol and action != "stocks":
            raise APIError("Not found", 404)
        if method != expected_method:
            raise APIError("Method not allowed", 405)
        workspace_id = normalize_workspace(raw_id)
        persona = body.get("persona")
        if persona is not None and not isinstance(persona, str):
            raise APIError("persona ต้องเป็นข้อความ")
        if action == "persona" and persona not in PERSONAS:
            raise APIError("โหมดนักลงทุนไม่ถูกต้อง (เลือก dividend หรือ momentum)")
        force = body.get("force_refresh", False)
        if action == "analyze" and not isinstance(force, bool):
            raise APIError("force_refresh ต้องเป็น true หรือ false")
        with self.lock:
            if workspace_id == "SERVER-ERROR":
                raise APIError("[OFFLINE FIXTURE] จำลองโหลดพอร์ตไม่สำเร็จ กรุณาลองใหม่", 503)
            workspace = self.workspace(workspace_id)
            if action is None:
                analyses = self.results(workspace, cached_only=True)
                return {"ok": True, "workspace": deepcopy(workspace), "analyses": analyses,
                        "summary": summary(analyses) if analyses else None, "max_symbols": MAX_SYMBOLS}
            if action == "persona" and workspace_id == "FAIL-PERSONA":
                raise APIError("[OFFLINE FIXTURE] จำลองบันทึกโหมดนักลงทุนไม่สำเร็จ", 503)
            if action == "stocks":
                symbol = normalize_symbol(raw_symbol if method == "DELETE" else body.get("symbol", ""))
                if method == "DELETE":
                    if symbol not in workspace["symbols"]:
                        raise APIError(f"ไม่พบ {symbol} ในพอร์ตนี้")
                    workspace["symbols"].remove(symbol)
                    for mode in PERSONAS:
                        self.cache.pop((workspace_id, symbol, mode), None)
                    message = f"ลบ {symbol} ออกจากพอร์ตแล้ว"
                else:
                    if symbol in workspace["symbols"]:
                        raise APIError(f"{symbol} อยู่ในพอร์ตนี้แล้ว")
                    if len(workspace["symbols"]) >= MAX_SYMBOLS:
                        raise APIError(f"พอร์ตนี้มีหุ้นครบ {MAX_SYMBOLS} ตัวแล้ว กรุณาลบตัวที่ไม่ใช้ก่อน")
                    workspace["symbols"].append(symbol)
                    if persona in PERSONAS:
                        workspace["persona"] = persona
                    message = f"เพิ่ม {symbol} เข้าพอร์ตแล้ว"
                workspace["updated_at"] = now_iso()
                return {"ok": True, "workspace": deepcopy(workspace), "message": message}
            if persona in PERSONAS:
                workspace["persona"] = persona
                workspace["updated_at"] = now_iso()
            if action == "persona":
                return {"ok": True, "workspace": deepcopy(workspace)}
            if not workspace["symbols"]:
                raise APIError("พอร์ตนี้ยังไม่มีหุ้น กรุณาเพิ่มหุ้นก่อนวิเคราะห์หรือส่งรายงาน")
            results = self.results(workspace, force=force if action == "analyze" else False)
            if action == "analyze":
                return {"ok": True, "workspace": deepcopy(workspace), "results": results,
                        "summary": summary(results), "sentiment": sentiment_fixture(results),
                        "force_refresh": force}
            return {"ok": True, "message": "OFFLINE MOCK SUCCESS — จำลองส่งรายงานเท่านั้น ไม่มีการส่ง SNS หรืออีเมลจริง",
                    "message_id": f"offline-mock-{uuid4()}", "summary": summary(results)}


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "OfflineDashboardPreview/1.0"

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def respond(self, status: int, payload: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(payload)

    def json_response(self, status: int, payload: dict):
        self.respond(status, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def read_body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise APIError("Transfer-Encoding is not supported", 400)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1 or (lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0])):
            raise APIError("Invalid Content-Length")
        size = int(lengths[0]) if lengths else 0
        if size > MAX_BODY_BYTES:
            raise APIError("JSON body is too large", 413)
        if not size:
            return {}
        if self.headers.get_content_type() != "application/json":
            raise APIError("Use Content-Type: application/json", 415)
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise APIError("Incomplete JSON body")
        try:
            body = json.loads(raw.decode("utf-8"), parse_constant=self.reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise APIError("Invalid JSON body") from None
        if not isinstance(body, dict):
            raise APIError("JSON body must be an object")
        return body

    @staticmethod
    def reject_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")

    def handle_request(self):
        try:
            target = urlsplit(self.path)
            path = unquote(target.path, errors="strict")
            if (target.scheme or target.netloc or target.fragment or not path.startswith("/")
                    or "\\" in path or any(ord(char) < 32 for char in path)
                    or any(part in (".", "..") for part in path.split("/"))):
                raise APIError("Invalid path")
            if path in ("/", "/index.html") and self.command == "GET":
                try:
                    html = TEMPLATE_PATH.read_bytes()
                except OSError:
                    raise APIError("Dashboard template is unavailable", 503) from None
                self.respond(200, html, "text/html; charset=utf-8")
            elif path == "/favicon.ico" and self.command == "GET":
                self.respond(204, b"", "image/x-icon")
            else:
                time.sleep(0.25)
                body = self.read_body() if self.command == "POST" else {}
                self.json_response(200, self.server.state.dispatch(self.command, path, body))
        except APIError as exc:
            self.json_response(exc.status, {"ok": False, "error": str(exc)})
        except (ValueError, UnicodeError):
            self.json_response(400, {"ok": False, "error": "Invalid request"})
        except TimeoutError:
            self.json_response(408, {"ok": False, "error": "Request timed out"})
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request

    def do_HEAD(self):
        self.json_response(405, {"ok": False, "error": "Method not allowed"})

    do_PUT = do_HEAD
    do_PATCH = do_HEAD
    do_OPTIONS = do_HEAD


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main():
    parser = argparse.ArgumentParser(description=BANNER)
    parser.add_argument("--port", type=port_number, default=8765, help="localhost port (default: 8765)")
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    except OSError as exc:
        parser.exit(1, f"Cannot start offline preview: {exc}\n")
    server.state = PreviewState()
    with server:
        print(BANNER, flush=True)
        print(f"http://127.0.0.1:{args.port}/", flush=True)
        print("DEMO-PORT: cached fixtures | SERVER-ERROR: 503 | FAIL-PERSONA: persona 503 | BAD: stock error", flush=True)
        print("Memory only; restart to reset. External browser resources are blocked for offline safety.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
