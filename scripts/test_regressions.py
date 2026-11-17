import asyncio
import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analyzer
import app
import db_and_notify as db
import preflight


class MemoryTable:
    def __init__(self):
        self.items = {}
        self.writes = 0

    def put_item(self, *, Item):
        self.items[(Item["pk"], Item["sk"])] = TypeSerializer().serialize(Item)
        self.writes += 1
        return {}

    def get_item(self, *, Key):
        stored = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": TypeDeserializer().deserialize(stored)} if stored else {}


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.table = MemoryTable()
        self.market = {
            "symbol": "PTT.BK",
            "indicators": {"price": 34.5, "change_pct": -0.25, "volume": 12345},
            "spark": [33.75, 34.0, 34.5],
            "news": [{"title": "ข่าวทดสอบ"}],
        }
        self.outcome = {
            "ai": {"score": 60, "signal": "WATCH", "risk_level": "MEDIUM"},
            "cost": analyzer.calculate_cost(1200, 300),
            "source": "bedrock",
            "analyzed_at": "2026-11-17T10:15:00+00:00",
        }
        self.analysis = {**self.market, **self.outcome, "cache_hit": False}
        self.enterContext(patch.object(db, "_table", self.table))
        self.clock = self.enterContext(patch.object(db.time, "time", return_value=1000))
        self.enterContext(patch.object(db, "CACHE_TTL_SECONDS", 600))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Unexpected network access")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Unexpected network access")))

    def test_nested_numbers_serialize_without_mutating_input(self):
        self.analysis["metadata"] = {
            "precise": Decimal("0.1234567890123456789"),
            "enabled": True,
            "missing": None,
            "values": (0.0, -1.25, 2),
        }
        original = copy.deepcopy(self.analysis)
        db.put_analysis("test", "PTT.BK", "dividend", self.analysis)
        stored = self.table.get_item(Key={"pk": "WORKSPACE#TEST", "sk": "ANALYSIS#PTT.BK#dividend"})["Item"]
        data = stored["analysis_data"]
        self.assertEqual(data["indicators"]["price"], Decimal("34.5"))
        self.assertEqual(data["spark"], [Decimal("33.75"), Decimal("34.0"), Decimal("34.5")])
        self.assertEqual(data["cost"]["usd"], Decimal(str(self.analysis["cost"]["usd"])))
        self.assertEqual(data["metadata"]["precise"], original["metadata"]["precise"])
        self.assertIs(data["metadata"]["enabled"], True)
        self.assertIsNone(data["metadata"]["missing"])
        self.assertEqual(data["metadata"]["values"], [Decimal("0.0"), Decimal("-1.25"), Decimal("2")])
        self.assertEqual(stored["ttl"], 1600)
        self.assertEqual(self.analysis, original)

    def test_cache_round_trip_is_json_serializable(self):
        db.put_analysis("TEST", "PTT.BK", "dividend", self.analysis)
        cached = db.get_cached_analysis("test", "PTT.BK", "dividend")
        self.assertEqual(cached, {**self.analysis, "cache_hit": True})
        self.assertEqual(json.loads(json.dumps(cached)), cached)
        self.assertFalse(self.analysis["cache_hit"])

    def test_missing_and_expired_cache_are_misses(self):
        self.assertIsNone(db.get_cached_analysis("TEST", "PTT.BK", "dividend"))
        db.put_analysis("TEST", "PTT.BK", "dividend", self.analysis)
        self.clock.return_value = 1601
        self.assertIsNone(db.get_cached_analysis("TEST", "PTT.BK", "dividend"))

    def test_result_without_ai_is_not_reused(self):
        db.put_analysis("TEST", "PTT.BK", "dividend", {**self.analysis, "ai": {}})
        self.assertIsNone(db.get_cached_analysis("TEST", "PTT.BK", "dividend"))

    def test_workspaces_symbols_and_personas_have_separate_cache_keys(self):
        for workspace, symbol, persona in [
            ("TEST", "PTT.BK", "dividend"),
            ("OTHER", "PTT.BK", "dividend"),
            ("TEST", "AAPL", "dividend"),
            ("TEST", "PTT.BK", "momentum"),
        ]:
            db.put_analysis(workspace, symbol, persona, self.analysis)
        self.assertEqual(len(self.table.items), 4)
        db.put_analysis("TEST", "PTT.BK", "dividend", {**self.analysis, "source": "gemini_fallback"})
        self.assertEqual(len(self.table.items), 4)
        self.assertEqual(db.get_cached_analysis("TEST", "PTT.BK", "dividend")["source"], "gemini_fallback")
        self.assertEqual(db.get_cached_analysis("OTHER", "PTT.BK", "dividend")["source"], "bedrock")
        self.assertEqual(db.get_cached_analysis("TEST", "AAPL", "dividend")["source"], "bedrock")
        self.assertEqual(db.get_cached_analysis("TEST", "PTT.BK", "momentum")["source"], "bedrock")

    def test_app_reuses_cache_and_force_refresh_reanalyzes(self):
        with (
            patch.object(app.market_data, "fetch_market_data", return_value=self.market) as fetch,
            patch.object(app.analyzer, "analyze_stock", return_value=self.outcome) as analyze,
        ):
            first = app._analyze_symbol("TEST", "PTT.BK", "dividend", False)
            cached = app._analyze_symbol("TEST", "PTT.BK", "dividend", False)
            fresh = app._analyze_symbol("TEST", "PTT.BK", "dividend", True)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(cached["cache_hit"])
        self.assertFalse(fresh["cache_hit"])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(analyze.call_count, 2)
        self.assertEqual(self.table.writes, 2)

    def test_workspace_api_returns_persisted_analysis(self):
        db.save_watchlist("TEST", ["PTT.BK"], "dividend")
        db.put_analysis("TEST", "PTT.BK", "dividend", self.analysis)
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(app.get_workspace("TEST"))
        body = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["analyses"][0]["cache_hit"])
        self.assertEqual(body["analyses"][0]["indicators"]["price"], 34.5)
        self.assertEqual(body["summary"]["analyzed_count"], 1)

    def test_cache_write_failure_still_returns_live_analysis(self):
        with (
            patch.object(app.market_data, "fetch_market_data", return_value=self.market),
            patch.object(app.analyzer, "analyze_stock", return_value=self.outcome),
            patch.object(self.table, "put_item", side_effect=RuntimeError("Storage unavailable")),
            self.assertLogs(app.logger, level="ERROR"),
        ):
            result = app._analyze_symbol("TEST", "PTT.BK", "dividend", True)
        self.assertEqual(result["ai"], self.outcome["ai"])
        self.assertFalse(result["cache_hit"])


class ReportArchiveTests(unittest.TestCase):
    """สำเนารายงานลง S3: path ต้องคงที่ต่อวัน/พอร์ต และต้องไม่ทำรายงานอีเมลล้มเหลว"""

    def setUp(self):
        self.s3 = MagicMock()
        self.enterContext(patch.object(db, "_s3", self.s3))
        self.enterContext(patch.object(db, "REPORT_BUCKET", "copilot-reports"))

    def test_report_copy_uses_daily_key_and_returns_s3_uri(self):
        uri = db.export_report_json(
            "test",
            "dividend",
            [{"symbol": "PTT.BK", "indicators": {"price": Decimal("34.5")}}],
            {"avg_score": 60, "counts": {"BUY": 0, "WATCH": 1, "SELL": 0}},
            "scheduled",
        )
        self.assertRegex(uri, r"^s3://copilot-reports/reports/TEST/\d{4}-\d{2}-\d{2}/scheduled\.json$")
        call = self.s3.put_object.call_args.kwargs
        self.assertEqual(call["Bucket"], "copilot-reports")
        self.assertEqual(call["ContentType"], "application/json; charset=utf-8")
        payload = json.loads(call["Body"].decode("utf-8"))
        self.assertEqual(payload["report_kind"], "scheduled")
        self.assertEqual(payload["results"][0]["indicators"]["price"], 34.5)

    def test_report_email_has_bull_bear_technicals_and_links(self):
        results = [
            {
                "symbol": "PTT.BK",
                "name": "PTT",
                "currency": "THB",
                "source": "bedrock",
                "model_id": "amazon.nova-lite-v1:0",
                "indicators": {"price": 34.5, "change_pct": 1.25, "rsi14": 55.2, "sma20": 33.9},
                "cost": {"usd": 0.00003, "thb": 0.0011},
                "ai": {
                    "score": 72,
                    "signal": "BUY",
                    "risk_level": "LOW",
                    "action_plan": {"entry_zone": "33.8", "stop_loss": "32.5", "take_profit": "37.0"},
                    "catalysts": ["กำไรโต"],
                    "risks": ["ราคาน้ำมันลด"],
                },
            }
        ]
        summary = {
            "avg_score": 72.0,
            "counts": {"BUY": 1, "WATCH": 0, "SELL": 0},
            "risk_counts": {"LOW": 1, "MEDIUM": 0, "HIGH": 0},
            "analyzed_count": 1,
            "total_cost_thb": 0.0011,
            "verdict": "โซนบวก",
            "highlights": [{"symbol": "PTT.BK", "score": 72, "signal": "BUY"}],
        }
        subject, message = db.build_report_email(
            "DEMO", "dividend", results, summary, "s3://b/reports/DEMO/d/manual.json", "https://x.lambda-url.us-east-1.on.aws/"
        )
        assert subject.isascii(), subject  # SNS ปฏิเสธ Subject ที่ไม่ใช่ ASCII
        for marker in ("🐂 ปัจจัยหนุน", "🐻 ปัจจัยกดดัน", "📊 RSI14 55.2", "🏆 หุ้นเด่น", "🔗 เปิด Dashboard: https://x"):
            assert marker in message, marker
        assert "s3://b/reports/DEMO/d/manual.json" in message

    def test_s3_console_url_from_uri(self):
        url = app._s3_console_url("s3://copilot-reports/reports/DEMO/2026-11-17/manual.json")
        assert url.startswith("https://s3.console.aws.amazon.com/s3/object/copilot-reports")
        assert "prefix=reports%2FDEMO%2F2026-11-17%2Fmanual.json" in url
        assert app._s3_console_url("") == ""

    def test_missing_bucket_or_s3_error_never_breaks_report(self):
        with patch.object(db, "REPORT_BUCKET", ""):
            self.assertEqual(db.export_report_json("TEST", "dividend", [], {}, "manual"), "")
        self.s3.put_object.assert_not_called()

        self.s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "simulated"}}, "PutObject"
        )
        with self.assertLogs(db.logger, level="WARNING"):
            self.assertEqual(db.export_report_json("TEST", "dividend", [], {}, "manual"), "")


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.clients = {service: MagicMock() for service in (
            "sts", "iam", "cloudformation", "s3", "lambda", "dynamodb", "sns", "events", "logs", "bedrock-runtime"
        )}
        self.clients["sts"].get_caller_identity.return_value = {
            "Account": "000000000000",
            "Arn": "arn:aws:sts::000000000000:assumed-role/voclabs/test",
        }
        self.clients["iam"].get_role.return_value = {
            "Role": {
                "Arn": "arn:aws:iam::000000000000:role/LabRole",
                "AssumeRolePolicyDocument": {"Statement": [{"Principal": {"Service": "lambda.amazonaws.com"}}]},
            }
        }
        self.clients["lambda"].get_function_url_config.side_effect = self.error("ResourceNotFoundException")
        self.clients["bedrock-runtime"].converse.return_value = {"usage": {"inputTokens": 1, "outputTokens": 1}}
        self.session = MagicMock()
        self.session.client.side_effect = self.clients.__getitem__
        self.enterContext(patch.object(preflight.boto3, "Session", return_value=self.session))
        self.enterContext(patch.object(preflight, "results", []))
        self.enterContext(patch.object(sys, "argv", ["preflight.py", "--region", "us-east-1"]))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Unexpected network access")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Unexpected network access")))

    @staticmethod
    def error(code):
        return ClientError({"Error": {"Code": code, "Message": "simulated error"}}, "OfflineCheck")

    def run_preflight(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = preflight.main()
        return code, output.getvalue()

    def test_ready_output_uses_built_template(self):
        code, output = self.run_preflight()
        self.assertEqual(code, 0)
        self.assertIn("sam deploy --guided -t .aws-sam/build/template.yaml", output)
        self.assertNotIn("sam deploy --guided -t template.learner-lab.yaml", output)
        self.assertFalse(any(status == preflight.FAIL for _, status, _ in preflight.results))
        self.clients["bedrock-runtime"].converse.assert_called_once()

    def test_missing_role_blocks_deploy(self):
        self.clients["iam"].get_role.side_effect = self.error("NoSuchEntity")
        code, output = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertIn("LabRole", output)

    def test_role_access_denied_blocks_deploy(self):
        self.clients["iam"].get_role.side_effect = self.error("AccessDenied")
        self.assertEqual(self.run_preflight()[0], 1)

    def test_role_without_lambda_trust_blocks_deploy(self):
        self.clients["iam"].get_role.return_value["Role"]["AssumeRolePolicyDocument"] = {
            "Statement": [{"Principal": {"Service": "ec2.amazonaws.com"}}]
        }
        self.assertEqual(self.run_preflight()[0], 1)

    def test_bedrock_denied_allows_fallback(self):
        self.clients["bedrock-runtime"].converse.side_effect = self.error("AccessDeniedException")
        code, output = self.run_preflight()
        self.assertEqual(code, 0)
        self.assertIn("Gemini", output)
        self.assertIn("rule-based", output)

    def test_core_service_failure_blocks_deploy(self):
        self.clients["dynamodb"].list_tables.side_effect = self.error("AccessDeniedException")
        self.assertEqual(self.run_preflight()[0], 1)

    def test_function_url_permission_denied_blocks_deploy(self):
        self.clients["lambda"].get_function_url_config.side_effect = self.error("AccessDeniedException")
        self.assertEqual(self.run_preflight()[0], 1)

    def test_invalid_credentials_stop_service_checks(self):
        self.clients["sts"].get_caller_identity.side_effect = self.error("ExpiredToken")
        self.assertEqual(self.run_preflight()[0], 1)
        self.clients["iam"].get_role.assert_not_called()
        self.clients["bedrock-runtime"].converse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
