#!/usr/bin/env bash
# deploy_learnerlab.sh — ติดตั้ง AI Equity Co-Pilot ขึ้น AWS Academy Learner Lab ในคำสั่งเดียว
#
# ใช้ได้ทั้งใน AWS CloudShell (แนะนำ: credential พร้อมใช้, ไม่ต้องลงอะไรในเครื่อง)
# และบนเครื่องตัวเอง (Linux / macOS / WSL / Git Bash)
#
# ตัวอย่าง:
#   bash scripts/deploy_learnerlab.sh --email me@example.com
#   bash scripts/deploy_learnerlab.sh --stack group7-demo --model us.amazon.nova-lite-v1:0
#   bash scripts/deploy_learnerlab.sh --skip-preflight
#   bash scripts/deploy_learnerlab.sh --delete

set -euo pipefail

cd "$(dirname "$0")/.."

STACK_NAME="${STACK_NAME:-ai-equity-copilot}"
REGION="${AWS_REGION:-us-east-1}"
MODEL="${BEDROCK_MODEL_ID:-amazon.nova-lite-v1:0}"
EMAIL="${ALERT_EMAIL:-}"
TEMPLATE="template.learner-lab.yaml"
SKIP_PREFLIGHT=0
DO_DELETE=0

usage() {
  cat <<'EOF'
วิธีใช้: bash scripts/deploy_learnerlab.sh [options]

  --email <อีเมล>      อีเมลรับรายงาน SNS (ไม่ใส่ก็ได้)
  --stack <ชื่อ>       ชื่อ CloudFormation stack (ค่าเริ่มต้น: ai-equity-copilot)
  --region <region>    region ของ Learner Lab (ค่าเริ่มต้น: us-east-1)
  --model <model-id>   โมเดล Bedrock (ค่าเริ่มต้น: amazon.nova-lite-v1:0)
  --skip-preflight     ข้ามการตรวจสิทธิ์ก่อน deploy
  --delete             ลบ stack ทั้งหมด (ถามยืนยันครั้งเดียว)
  -h, --help           แสดงข้อความนี้

หมายเหตุ: ต้อง Start Lab ให้สถานะเขียวก่อน (credential อายุ 4 ชั่วโมง)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --email) EMAIL="${2:-}"; shift 2 ;;
    --stack) STACK_NAME="${2:-}"; shift 2 ;;
    --region) REGION="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --skip-preflight) SKIP_PREFLIGHT=1; shift ;;
    --delete) DO_DELETE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ไม่รู้จักออปชัน: $1 (ใช้ --help ดูตัวเลือก)"; exit 2 ;;
  esac
done

info() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m    OK\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m    WARN\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m    ERROR\033[0m %s\n' "$1"; exit 1; }

export PATH="$HOME/.local/bin:$PATH"
export AWS_REGION="$REGION"
export AWS_DEFAULT_REGION="$REGION"

# ---------------------------------------------------------------- credential
info "ตรวจ credential และ region ($REGION)"
command -v aws >/dev/null 2>&1 || die "ไม่พบ aws CLI — ใช้ AWS CloudShell หรือติดตั้ง AWS CLI ก่อน"
IDENTITY="$(aws sts get-caller-identity --output json 2>/dev/null || true)"
if [[ -z "$IDENTITY" ]]; then
  die "credential ใช้งานไม่ได้: กด Start Lab ใน AWS Academy แล้วเปิด CloudShell ใหม่ (session อายุ 4 ชม.)"
fi
ACCOUNT="$(printf '%s' "$IDENTITY" | sed -n 's/.*"Account": *"\([0-9]*\)".*/\1/p')"
ok "account ${ACCOUNT:-unknown}"

# ---------------------------------------------------------------- delete mode
if [[ "$DO_DELETE" == "1" ]]; then
  info "ลบ stack $STACK_NAME (region $REGION)"
  command -v sam >/dev/null 2>&1 || die "ไม่พบ sam CLI"
  sam delete --stack-name "$STACK_NAME" --region "$REGION" --no-prompts
  ok "ลบเรียบร้อย"
  exit 0
fi

# ---------------------------------------------------------------- sam CLI
info "ตรวจ AWS SAM CLI"
if ! command -v sam >/dev/null 2>&1; then
  warn "ไม่พบ sam — กำลังติดตั้งด้วย pip (ใช้เวลา 1-2 นาที)"
  command -v pip3 >/dev/null 2>&1 || die "ไม่พบ pip3 — ใช้ CloudShell หรือติดตั้ง Python ก่อน"
  pip3 install --quiet --user aws-sam-cli || die "ติดตั้ง sam ไม่สำเร็จ (ลองใช้ CloudShell)"
  hash -r
  command -v sam >/dev/null 2>&1 || die "ติดตั้ง sam แล้วแต่ไม่พบใน PATH (ลองเปิด terminal ใหม่)"
fi
ok "$(sam --version 2>/dev/null | head -1)"

# ---------------------------------------------------------------- build mode
# Lambda runtime ต้องตรงกับ Python ที่ใช้ build ไม่งั้น pandas/numpy จะได้ wheel ผิดเวอร์ชัน
RUNTIME="$(grep -m1 'Runtime:' "$TEMPLATE" | awk '{print $2}')"
RUNTIME="${RUNTIME:-python3.12}"
PY_BIN="$RUNTIME"          # เช่น python3.12
WANT_VER="${RUNTIME#python}"  # เช่น 3.12
PY312=""

for candidate in "$PY_BIN" python3; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  HAVE_VER="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  if [[ "$HAVE_VER" == "$WANT_VER" ]]; then
    PY312="$candidate"
    break
  fi
done

BUILD_MODE=""
if [[ -n "$PY312" ]]; then
  BUILD_MODE="native"
  # SAM จะเรียกหา interpreter ชื่อ python3.12 ตรงๆ ถ้าในเครื่องมีแต่ python3 ให้ทำ shim ชั่วคราว
  if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    SHIM_DIR="$(mktemp -d)"
    ln -sf "$(command -v "$PY312")" "$SHIM_DIR/$PY_BIN"
    export PATH="$SHIM_DIR:$PATH"
  fi
  ok "build ด้วย $PY312 (ตรงกับ runtime $RUNTIME)"
elif docker info >/dev/null 2>&1; then
  BUILD_MODE="container"
  ok "ไม่พบ $RUNTIME แต่มี Docker — จะ build ใน container"
else
  die "ต้องมี $RUNTIME หรือ Docker เพื่อ build (CloudShell รุ่นใหม่มักมี 3.12; ถ้าไม่มีให้รันสคริปต์นี้บนเครื่องตัวเองตาม SETUP_LEARNER_LAB.md)"
fi

# ---------------------------------------------------------------- preflight
if [[ "$SKIP_PREFLIGHT" == "0" ]]; then
  info "ตรวจความพร้อมก่อน deploy (preflight)"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import boto3" 2>/dev/null || pip3 install --quiet --user boto3 || true
    if ! python3 scripts/preflight.py --region "$REGION" --model "$MODEL"; then
      die "preflight ไม่ผ่าน (ดูรายการ ❌ ด้านบน) — แก้ให้ผ่านก่อน หรือใช้ --skip-preflight"
    fi
  else
    warn "ไม่พบ python3 — ข้าม preflight"
  fi
else
  warn "ข้าม preflight ตามคำสั่ง"
fi

# ---------------------------------------------------------------- build
info "sam build ($BUILD_MODE)"
if [[ "$BUILD_MODE" == "container" ]]; then
  sam build --use-container --template-file "$TEMPLATE"
else
  sam build --template-file "$TEMPLATE"
fi
ok "build เสร็จ"

# ---------------------------------------------------------------- deploy
info "sam deploy → stack: $STACK_NAME"
sam deploy \
  --template-file "$TEMPLATE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides "AlertEmail=$EMAIL" "BedrockModelId=$MODEL"

# ---------------------------------------------------------------- outputs
info "ผลลัพธ์"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}" \
  --output table

DASHBOARD_URL="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text)"

printf '\n\033[1;32mเรียบร้อย! เปิดหน้าเว็บได้ที่:\033[0m\n  %s\n' "${DASHBOARD_URL:-<ดูใน CloudFormation Outputs>}"
if [[ -n "$EMAIL" ]]; then
  printf '\nอย่าลืมกด Confirm subscription ในอีเมล (%s) ก่อนกดส่งรายงาน\n' "$EMAIL"
fi
printf '\nลบทั้งหมดภายหลัง: bash scripts/deploy_learnerlab.sh --delete\n'
