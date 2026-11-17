"""app.py — Entrypoint เดียวที่รองรับทั้งสองบทบาท

1) HTTP (Lambda Function URL) -> FastAPI ผ่าน Mangum : เสิร์ฟหน้าเว็บ + REST API
2) EventBridge Scheduled Event -> วิเคราะห์ทุก Workspace อัตโนมัติและส่งอีเมลสรุปผ่าน SNS

ทุกรายงานที่ส่งออกจะเก็บสำเนาเป็น JSON ลง Amazon S3 (reports/...) เพื่อตรวจย้อนหลัง
ไม่ใช้ S3 static hosting และไม่ใช้ API Gateway ตามข้อกำหนดของโปรเจกต์
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from mangum import Mangum

import analyzer
import db_and_notify as db
import market_data
import sentiment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("equity-copilot")

USD_TO_THB = float(os.environ.get("USD_TO_THB", "36.0"))
MAX_WORKERS = 5
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "index.html"

app = FastAPI(title="AI Equity Co-Pilot", version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_html_cache: str = ""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _read_json(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    return {}


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"ok": False, "error": message})


def _index_html() -> str:
    global _html_cache
    if not _html_cache:
        try:
            _html_cache = TEMPLATE_PATH.read_text(encoding="utf-8")
        except OSError:
            logger.exception("อ่านไฟล์ templates/index.html ไม่สำเร็จ")
            _html_cache = (
                "<html><body style='font-family:sans-serif;padding:2rem'>"
                "<h2>ไม่พบไฟล์หน้าเว็บ (templates/index.html)</h2>"
                "<p>กรุณาตรวจสอบว่าไฟล์ถูกแพ็กเข้า Lambda แล้ว</p></body></html>"
            )
    return _html_cache


def _sentiment(results: list[dict]) -> dict:
    """Greed & Fear Index — คำนวณไม่ได้ก็ต้องไม่ทำให้คำขอล้ม"""
    try:
        return sentiment.compute(results)
    except Exception:  # noqa: BLE001
        logger.exception("คำนวณ Greed & Fear Index ไม่สำเร็จ")
        return {"available": False, "score": None, "components": [], "drivers": [], "history": []}


def _summary(results: list[dict]) -> dict:
    valid = [item for item in results if item.get("ai") and not item.get("error")]
    counts = {"BUY": 0, "WATCH": 0, "SELL": 0}
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    scores: list[int] = []
    total_usd = 0.0
    for item in valid:
        ai = item.get("ai") or {}
        signal = str(ai.get("signal") or "").upper()
        if signal in counts:
            counts[signal] += 1
        risk = str(ai.get("risk_level") or "MEDIUM").upper()
        if risk in risk_counts:
            risk_counts[risk] += 1
        try:
            scores.append(int(ai.get("score") or 0))
        except (TypeError, ValueError):
            pass
        total_usd += float((item.get("cost") or {}).get("usd") or 0.0)

    average = round(sum(scores) / len(scores), 1) if scores else 0.0
    if average >= 65:
        verdict = "พอร์ตโดยรวมอยู่ในโซนบวก ควรรักษาสถานะและเน้นหุ้นที่ได้คะแนนสูง"
    elif average >= 45:
        verdict = "พอร์ตโดยรวมเป็นกลาง รอจังหวะที่ชัดเจนก่อนเพิ่มน้ำหนักการลงทุน"
    else:
        verdict = "พอร์ตโดยรวมมีความเสี่ยงสูง ควรลดสถานะและทบทวนหุ้นที่คะแนนต่ำ"

    highlights = sorted(
        (
            {
                "symbol": item.get("symbol"),
                "score": (item.get("ai") or {}).get("score", 0),
                "signal": (item.get("ai") or {}).get("signal", "WATCH"),
            }
            for item in valid
        ),
        key=lambda entry: entry["score"],
        reverse=True,
    )[:3]

    return {
        "avg_score": average,
        "counts": counts,
        "risk_counts": risk_counts,
        "analyzed_count": len(valid),
        "total_cost_usd": round(total_usd, 6),
        "total_cost_thb": round(total_usd * USD_TO_THB, 4),
        "verdict": verdict,
        "highlights": highlights,
    }


def _analyze_symbol(workspace_id: str, symbol: str, persona: str, force: bool) -> dict:
    if not force:
        cached = db.get_cached_analysis(workspace_id, symbol, persona)
        if cached:
            return cached

    market = market_data.fetch_market_data(symbol)
    outcome = analyzer.analyze_stock(market, persona)
    result = {**market, **outcome, "cache_hit": False}

    try:
        db.put_analysis(workspace_id, symbol, persona, result)
    except Exception:  # noqa: BLE001 - cache เขียนไม่ได้ก็ยังคืนผลให้ผู้ใช้ได้
        logger.exception("บันทึกผลวิเคราะห์ลง DynamoDB ไม่สำเร็จ (%s)", symbol)

    return result


def _s3_console_url(uri: str) -> str:
    """แปลง s3://bucket/key เป็นลิงก์คอนโซล S3 สำหรับคลิกดูไฟล์บนหน้าเว็บ"""
    if not uri.startswith("s3://"):
        return ""
    bucket, _, key = uri[len("s3://"):].partition("/")
    if not bucket or not key:
        return ""
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    return (
        f"https://s3.console.aws.amazon.com/s3/object/{quote(bucket)}"
        f"?region={quote(region)}&prefix={quote(key, safe='')}"
    )


def _persist_persona(workspace: dict, persona: str) -> dict:
    """บันทึกโหมดนักลงทุนใหม่ ถ้าเขียน DynamoDB ไม่ได้ก็ยังวิเคราะห์ต่อได้"""
    if persona not in db.VALID_PERSONAS or persona == workspace.get("persona"):
        return workspace
    try:
        return db.save_watchlist(workspace["workspace_id"], workspace["symbols"], persona)
    except Exception:  # noqa: BLE001
        logger.exception("บันทึกโหมดนักลงทุนลง DynamoDB ไม่สำเร็จ")
        return {**workspace, "persona": persona}


def _collect_results(workspace_id: str, persona: str, force: bool) -> list[dict]:
    workspace = db.get_watchlist(workspace_id)
    symbols = workspace["symbols"]
    if not symbols:
        return []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_analyze_symbol, workspace["workspace_id"], symbol, persona, force): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results.append(future.result())
            except market_data.MarketDataError as exc:
                results.append({"symbol": symbol, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.exception("วิเคราะห์ %s ไม่สำเร็จ", symbol)
                results.append(
                    {
                        "symbol": symbol,
                        "error": f"วิเคราะห์ {symbol} ไม่สำเร็จชั่วคราว ({exc.__class__.__name__}) กรุณาลองใหม่",
                    }
                )

    order = {symbol: index for index, symbol in enumerate(symbols)}
    results.sort(key=lambda item: order.get(str(item.get("symbol")), 999))
    return results


# --------------------------------------------------------------------------
# HTTP Routes
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(content=_index_html())


@app.get("/api/workspace/{workspace_id}")
async def get_workspace(workspace_id: str) -> JSONResponse:
    try:
        workspace = db.get_watchlist(workspace_id)
        analyses = []
        for symbol in workspace["symbols"]:
            cached = db.get_cached_analysis(workspace["workspace_id"], symbol, workspace["persona"])
            if cached:
                analyses.append(cached)
        return JSONResponse(
            content={
                "ok": True,
                "workspace": workspace,
                "analyses": analyses,
                "summary": _summary(analyses) if analyses else None,
                "max_symbols": db.MAX_SYMBOLS,
            }
        )
    except db.WorkspaceError as exc:
        return _error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("โหลด Workspace ไม่สำเร็จ")
        return _error("โหลดพอร์ตไม่สำเร็จชั่วคราว กรุณาลองใหม่อีกครั้ง", 503)


@app.post("/api/workspace/{workspace_id}/stocks")
async def add_stock(workspace_id: str, request: Request) -> JSONResponse:
    body = _read_json(await _body(request))
    persona = body.get("persona") if body.get("persona") in db.VALID_PERSONAS else None
    try:
        symbol = market_data.normalize_symbol(str(body.get("symbol") or ""))
        workspace = db.add_symbol(workspace_id, symbol, persona)
        return JSONResponse(content={"ok": True, "workspace": workspace, "message": f"เพิ่ม {symbol} เข้าพอร์ตแล้ว"})
    except (market_data.MarketDataError, db.WorkspaceError) as exc:
        return _error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("เพิ่มหุ้นไม่สำเร็จ")
        return _error("เพิ่มหุ้นเข้าพอร์ตไม่สำเร็จชั่วคราว กรุณาลองใหม่", 503)


@app.delete("/api/workspace/{workspace_id}/stocks/{symbol}")
async def delete_stock(workspace_id: str, symbol: str) -> JSONResponse:
    try:
        normalized = market_data.normalize_symbol(symbol)
        workspace = db.remove_symbol(workspace_id, normalized)
        db.delete_analysis(workspace["workspace_id"], normalized, workspace["persona"])
        return JSONResponse(content={"ok": True, "workspace": workspace, "message": f"ลบ {normalized} ออกจากพอร์ตแล้ว"})
    except (market_data.MarketDataError, db.WorkspaceError) as exc:
        return _error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("ลบหุ้นไม่สำเร็จ")
        return _error("ลบหุ้นออกจากพอร์ตไม่สำเร็จชั่วคราว กรุณาลองใหม่", 503)


@app.post("/api/workspace/{workspace_id}/persona")
async def set_persona(workspace_id: str, request: Request) -> JSONResponse:
    body = _read_json(await _body(request))
    persona = str(body.get("persona") or "")
    if persona not in db.VALID_PERSONAS:
        return _error("โหมดนักลงทุนไม่ถูกต้อง (เลือก dividend หรือ momentum)")
    try:
        workspace = db.get_watchlist(workspace_id)
        workspace = db.save_watchlist(workspace["workspace_id"], workspace["symbols"], persona)
        return JSONResponse(content={"ok": True, "workspace": workspace})
    except db.WorkspaceError as exc:
        return _error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("บันทึกโหมดนักลงทุนไม่สำเร็จ")
        return _error("บันทึกโหมดนักลงทุนไม่สำเร็จชั่วคราว กรุณาลองใหม่", 503)


@app.post("/api/workspace/{workspace_id}/analyze")
async def analyze_workspace(workspace_id: str, request: Request) -> JSONResponse:
    body = _read_json(await _body(request))
    try:
        workspace = _persist_persona(db.get_watchlist(workspace_id), str(body.get("persona") or ""))
        if not workspace["symbols"]:
            return _error("พอร์ตนี้ยังไม่มีหุ้น กรุณาเพิ่มหุ้นก่อนกดวิเคราะห์")

        force = bool(body.get("force_refresh"))
        results = _collect_results(workspace["workspace_id"], workspace["persona"], force)
        summary = _summary(results)
        return JSONResponse(
            content={
                "ok": True,
                "workspace": workspace,
                "results": results,
                "summary": summary,
                "sentiment": _sentiment(results),
                "force_refresh": force,
            }
        )
    except db.WorkspaceError as exc:
        return _error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("วิเคราะห์พอร์ตไม่สำเร็จ")
        return _error("วิเคราะห์พอร์ตไม่สำเร็จชั่วคราว กรุณาลองใหม่อีกครั้ง", 503)


@app.post("/api/workspace/{workspace_id}/notify")
async def notify_workspace(workspace_id: str, request: Request) -> JSONResponse:
    body = _read_json(await _body(request))
    try:
        workspace = _persist_persona(db.get_watchlist(workspace_id), str(body.get("persona") or ""))
        if not workspace["symbols"]:
            return _error("พอร์ตนี้ยังไม่มีหุ้น กรุณาเพิ่มหุ้นก่อนส่งรายงาน")

        results = _collect_results(workspace["workspace_id"], workspace["persona"], False)
        summary = _summary(results)
        # เก็บสำเนาลง S3 ก่อนสร้างอีเมล เพื่อให้แนบลิงก์ไว้ในส่วนท้ายรายงานได้
        archive_uri = db.export_report_json(
            workspace["workspace_id"], workspace["persona"], results, summary, "manual"
        )
        subject, message = db.build_report_email(
            workspace["workspace_id"],
            workspace["persona"],
            results,
            summary,
            archive_uri,
            db.dashboard_url(),
            _sentiment(results),
        )
        message_id = db.send_email(subject, message)
        return JSONResponse(
            content={
                "ok": True,
                "message": "ส่งรายงานเข้าอีเมลที่ผูกกับ Amazon SNS แล้ว",
                "message_id": message_id,
                "summary": summary,
                "report_s3_uri": archive_uri,
                "report_s3_console_url": _s3_console_url(archive_uri),
            }
        )
    except db.WorkspaceError as exc:
        return _error(str(exc))
    except db.NotifyError as exc:
        return _error(str(exc), 502)
    except Exception:  # noqa: BLE001
        logger.exception("ส่งรายงานทางอีเมลไม่สำเร็จ")
        return _error("ส่งรายงานทางอีเมลไม่สำเร็จชั่วคราว กรุณาลองใหม่", 503)


# --------------------------------------------------------------------------
# EventBridge (Scheduled) Handler
# --------------------------------------------------------------------------
def _is_scheduled_event(event: dict) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("source") == "aws.events":
        return True
    if "detail-type" in event:
        return True
    return event.get("action") == "scheduled"


def run_scheduled_report() -> dict:
    workspaces = db.list_workspaces()
    if not workspaces:
        logger.info("ยังไม่มี Workspace ในระบบ ข้ามรอบนี้")
        return {"ok": True, "workspaces": 0, "message": "ไม่มีพอร์ตที่ต้องวิเคราะห์"}

    blocks: list[str] = []
    analyzed = 0
    changed = 0
    for workspace_id in workspaces:
        try:
            workspace = db.get_watchlist(workspace_id)
            # รอบอัตโนมัติต้องใช้ข้อมูลปิดตลาดจริง จึงบังคับดึงสดเสมอ
            # (ถ้าใช้ cache ผลที่วิเคราะห์ก่อนตลาดปิดอาจถูกส่งออกไปเป็นรายงานปิดวัน)
            results = _collect_results(workspace["workspace_id"], workspace["persona"], True)
            summary = _summary(results)
            analyzed += len(results)
            changed += summary["counts"]["BUY"] + summary["counts"]["SELL"]
            archive_uri = db.export_report_json(
                workspace["workspace_id"], workspace["persona"], results, summary, "scheduled"
            )
            _, message = db.build_report_email(
                workspace["workspace_id"],
                workspace["persona"],
                results,
                summary,
                archive_uri,
                db.dashboard_url(),
                _sentiment(results),
            )
            blocks.append(message)
        except Exception:  # noqa: BLE001 - Workspace เดียวพังต้องไม่ล้มทั้งรอบ
            logger.exception("วิเคราะห์ Workspace %s ไม่สำเร็จ", workspace_id)

    if not blocks:
        return {"ok": False, "workspaces": len(workspaces), "message": "วิเคราะห์ไม่สำเร็จทุกพอร์ต"}

    try:
        subject = (
            "[AI Equity Co-Pilot] Daily market close report "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        )
        db.send_email(subject, "\n\n".join(blocks))
    except db.NotifyError:
        logger.exception("ส่งอีเมลรอบอัตโนมัติไม่สำเร็จ")

    return {
        "ok": True,
        "workspaces": len(workspaces),
        "analyzed_symbols": analyzed,
        "notable_signals": changed,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _scheduled_handler(event: dict, context) -> dict:
    logger.info("เริ่มงานอัตโนมัติจาก EventBridge: %s", event.get("source") or event.get("detail-type"))
    result = run_scheduled_report()
    logger.info("จบงานอัตโนมัติ: %s", json.dumps(result, ensure_ascii=False))
    return result


# --------------------------------------------------------------------------
# AWS Lambda entrypoint
# --------------------------------------------------------------------------
_http_handler = Mangum(app, lifespan="off")


def handler(event, context=None):
    if _is_scheduled_event(event) and "requestContext" not in (event or {}):
        return _scheduled_handler(event, context)
    return _http_handler(event, context)
