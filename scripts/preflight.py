#!/usr/bin/env python3
"""preflight.py — ตรวจว่าบัญชี AWS นี้พร้อม deploy AI Equity Co-Pilot หรือไม่

ออกแบบมาสำหรับ **AWS Academy Learner Lab** เป็นหลัก (จำกัด region, ห้ามสร้าง IAM role,
สิทธิ์บางบริการถูกบล็อก) แต่ใช้กับบัญชี AWS ปกติได้เช่นกัน

หลักการ: เป็น read-only ทั้งหมด ยกเว้นการเรียก Bedrock 1 ครั้งด้วย maxTokens=8
(ต้นทุนประมาณ 0.000001 USD) เพื่อยืนยันว่าโมเดลเรียกได้จริง

วิธีใช้:
    python scripts/preflight.py
    python scripts/preflight.py --region us-east-1 --model amazon.nova-lite-v1:0

ต้องมี credential ในเครื่อง (aws configure) และติดตั้ง boto3 แล้ว:
    pip install boto3
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
except ImportError:  # pragma: no cover
    print("ยังไม่ได้ติดตั้ง boto3: รัน `pip install boto3` ก่อน")
    raise SystemExit(2)

try:  # ให้แสดงภาษาไทยได้บนคอนโซล Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str) -> None:
    results.append((name, status, detail))
    icon = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}[status]
    print(f"{icon} {name:<34} {detail}")


def check(name: str, fn) -> object | None:
    """เรียก fn() แล้วบันทึกผลเป็น PASS/FAIL โดยไม่ทำให้สคริปต์หยุด"""
    try:
        value = fn()
        record(name, PASS, "ok")
        return value
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", "")[:110]
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            record(name, FAIL, f"ถูกปฏิเสธสิทธิ์ ({code}) — {message}")
        else:
            record(name, FAIL, f"{code}: {message}")
    except NoCredentialsError:
        record(name, FAIL, "ไม่พบ credential — ตั้งค่า aws configure ก่อน")
    except BotoCoreError as exc:
        record(name, FAIL, f"{exc.__class__.__name__}: {str(exc)[:110]}")
    except Exception as exc:  # noqa: BLE001
        record(name, FAIL, f"{exc.__class__.__name__}: {str(exc)[:110]}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="ตรวจความพร้อมก่อน deploy")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION") or "us-east-1")
    parser.add_argument("--model", default="amazon.nova-lite-v1:0")
    parser.add_argument("--role-name", default="LabRole")
    args = parser.parse_args()

    print("=" * 78)
    print("AI Equity Co-Pilot — AWS Preflight Check")
    print("=" * 78)
    print(f"Region: {args.region}   Model: {args.model}   Role: {args.role_name}\n")

    session = boto3.Session(region_name=args.region)

    # 1) ตัวตนและ region
    identity = check("AWS credential & identity", lambda: session.client("sts").get_caller_identity())
    if not identity:
        print("\nหยุดทันที: credential ใช้งานไม่ได้ (Learner Lab ต้องกด Start Lab แล้วคัดลอกค่าใหม่)")
        return 1
    account = identity.get("Account", "?")
    arn = identity.get("Arn", "?")
    if "assumed-role/voclabs" in arn:
        record("ตรวจชนิดบัญชี", PASS, "AWS Academy / Vocareum (Learner Lab)")
    else:
        record("ตรวจชนิดบัญชี", PASS, f"บัญชีทั่วไป (account {account})")

    # 2) IAM role ที่จะใช้ (Learner Lab ห้ามสร้าง role ใหม่)
    role = check(
        f"IAM role '{args.role_name}' มีอยู่จริง",
        lambda: session.client("iam").get_role(RoleName=args.role_name),
    )
    if isinstance(role, dict):
        record("Role ที่ Lambda จะใช้", PASS, role["Role"]["Arn"])
        trust_policy = json.dumps(role["Role"].get("AssumeRolePolicyDocument") or {})
        if "lambda.amazonaws.com" in trust_policy:
            record("Role ยอมให้ Lambda สวมสิทธิ์", PASS, "ok")
        else:
            record(
                "Role ยอมให้ Lambda สวมสิทธิ์",
                FAIL,
                "trust policy ไม่มี lambda.amazonaws.com — Lambda จะสวม role นี้ไม่ได้",
            )

    # 3) บริการที่ SAM ต้องใช้ตอน deploy
    check("CloudFormation (SAM deploy)", lambda: session.client("cloudformation").list_stacks())
    check("S3 (bucket เก็บ artifact)", lambda: session.client("s3").list_buckets())
    check("Lambda", lambda: session.client("lambda").list_functions(MaxItems=1))
    check("DynamoDB", lambda: session.client("dynamodb").list_tables(Limit=1))
    check("SNS", lambda: session.client("sns").list_topics())
    check("EventBridge / Events", lambda: session.client("events").list_rules(Limit=1))
    check("CloudWatch Logs", lambda: session.client("logs").describe_log_groups(limit=1))

    # 4) Lambda Function URL (API ที่ SAM จะสร้าง) — ทดสอบสิทธิ์ด้วยชื่อฟังก์ชันที่ไม่มีอยู่
    url_check = check(
        "Lambda Function URL (สิทธิ์)",
        lambda: session.client("lambda").get_function_url_config(FunctionName="__preflight_not_exist__"),
    )
    if url_check is None:
        # ถ้า FAIL เพราะ ResourceNotFound แปลว่าสิทธิ์ผ่าน ให้แก้ข้อความให้ถูกต้อง
        for index, (name, status, detail) in enumerate(results):
            if name.startswith("Lambda Function URL") and status == FAIL and "ResourceNotFound" in detail:
                results[index] = (name, PASS, "ok (อนุญาตให้จัดการ Function URL)")
                print("   ↳ สิทธิ์ผ่าน (ได้ ResourceNotFound ซึ่งคาดไว้เพราะยังไม่มีฟังก์ชัน)")
                break

    # 5) Bedrock — ตัวชี้ขาดว่าโหมด AI จะทำงานเต็มหรือถอยไปใช้ rule-based
    bedrock_client = session.client("bedrock-runtime")
    def invoke_bedrock():
        return bedrock_client.converse(
            modelId=args.model,
            messages=[{"role": "user", "content": [{"text": "ตอบคำเดียว: OK"}]}],
            inferenceConfig={"maxTokens": 8, "temperature": 0},
        )

    bedrock = check("Bedrock (เรียกโมเดลจริง)", invoke_bedrock)
    if isinstance(bedrock, dict):
        usage = bedrock.get("usage", {})
        record(
            "Bedrock token ที่ใช้ทดสอบ",
            PASS,
            f"in={usage.get('inputTokens', 0)} out={usage.get('outputTokens', 0)}",
        )

    # 6) สรุป
    print("\n" + "=" * 78)
    failed = [item for item in results if item[1] == FAIL]
    core_failed = [
        item for item in failed
        if item[0].startswith(("CloudFormation", "Lambda", "DynamoDB", "SNS", "EventBridge", "S3"))
    ]
    bedrock_ok = any(item[0].startswith("Bedrock") and item[1] == PASS for item in results)

    if core_failed:
        print("ผลลัพธ์: ยัง deploy ไม่ได้ — ติดที่:")
        for name, _, detail in core_failed:
            print(f"  - {name}: {detail}")
        print("\nถ้าใช้ Learner Lab: กด Start Lab ให้สถานะเป็นสีเขียว แล้วคัดลอก credential ใหม่")
        print("ดูคู่มือใน SETUP_GUIDE.md หัวข้อ 'AWS Academy Learner Lab'")
        return 1

    print("ผลลัพธ์: ✅ พร้อม deploy (ผ่านทุกบริการที่ต้องสร้าง)")
    print("         Lambda ✅  DynamoDB ✅  EventBridge ✅  SNS ✅")
    if bedrock_ok:
        print("         Bedrock ✅ — ได้ผลวิเคราะห์จาก AI จริง (5 บริการครบ, Level 4 เต็มรูปแบบ)")
    else:
        print("         Bedrock ❌ — ยัง deploy ได้ (4 บริการที่ทำงานจริงตามเกณฑ์)")
        print("         ถ้าตั้ง Gemini API key ระบบจะใช้ AI สำรองก่อน แล้วจึงตกไป rule-based")
        print("         คำสั่งที่ใช้ต่อได้: bash scripts/deploy_learnerlab.sh --skip-preflight --gemini-key <key>")
    print("=" * 78)
    print("\nขั้นต่อไป (ทางลัดที่สคริปต์ทำให้ทั้งหมด):")
    print("  bash scripts/deploy_learnerlab.sh")
    print("หรือทำเองด้วย SAM CLI:")
    print("  sam build -t template.learner-lab.yaml")
    print("  sam deploy --guided -t template.learner-lab.yaml")
    print("  (ตอบ 'N' เมื่อถูกถามว่า Allow SAM CLI IAM role creation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
