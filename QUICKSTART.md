# ⚡ Quickstart — ติดตั้งใน AWS CloudShell (AWS Academy Learner Lab)

คู่มือฉบับรัดกุมสำหรับติดตั้งระบบ **AI Equity Co-Pilot** บน **AWS CloudShell** (Region: us-east-1) โดยไม่ต้องใช้ Docker และไม่ติดปัญหาพื้นที่ 1 GB ของ CloudShell เต็ม

---

## ขั้นตอนที่ 1: เตรียมสภาพแวดล้อมและ Clone โปรเจกต์ใน /tmp

เปิด **AWS Console** จากหน้า Learner Lab (ตรวจสอบว่าอยู่มุมขวาบนที่ Region **us-east-1**) กดไอคอน **CloudShell** แล้วก๊อปปี้ชุดคำสั่งนี้วางรันได้เลย:

```bash
# 1. ติดตั้ง Python 3.12 เพื่อสั่ง Build บนเครื่องตรงๆ ในไม่กี่วินาที (ไม่ต้องดึง Docker)
sudo dnf install -y python3.12 python3.12-pip

# 2. ย้ายไปทำงานใน /tmp (มีพื้นที่ว่าง ~10 GB) และดึงโค้ดล่าสุดจาก GitHub
export TMPDIR=/tmp PIP_CACHE_DIR=/tmp/pip-cache
rm -rf /tmp/aws-financial
cd /tmp
git clone https://github.com/Nattasit589/aws-financial.git
cd aws-financial
```

## ขั้นตอนที่ 2: รันสคริปต์ติดตั้งอัตโนมัติ

```bash
read -p "กรอกอีเมลจริงสำหรับรับแจ้งเตือน (เช่น name@gmail.com): " USER_EMAIL
bash scripts/deploy_learnerlab.sh --email "$USER_EMAIL"
```

สคริปต์จะทำให้ทั้งหมดนี้ในคำสั่งเดียว:

1. ตรวจ credential (ไม่ต้อง `aws configure` เพราะ CloudShell ล็อกอินอยู่แล้ว)
2. ตรวจ `sam` (ถ้าไม่มีจะติดตั้งให้)
3. เลือกวิธี build ที่ตรงกับ runtime `python3.12` (ใช้ Python 3.12 ที่เพิ่งติดตั้ง / Docker ถ้ามี)
4. ติดตั้ง `boto3` ถ้าจำเป็น แล้วรัน preflight ตรวจสิทธิ์ Bedrock + บริการที่ต้องใช้
5. `sam build` → `sam deploy` ด้วย `.aws-sam/build/template.yaml` (template ที่มีไลบรารีครบ) แบบไม่ต้องตอบคำถาม
6. พิมพ์ **DashboardUrl** ให้เปิดใช้งานทันที

> **หมายเหตุ:** หาก preflight แจ้งว่า Bedrock ถูกปฏิเสธสิทธิ์ (`AccessDeniedException`) ไม่ต้องกังวล ระบบจะสลับไปใช้โหมดวิเคราะห์สำรอง (Rule-based fallback) ให้อัตโนมัติและทำงานครบทุกฟีเจอร์

ออปชันเสริม: `--stack my-group` (เปลี่ยนชื่อ stack), `--model us.amazon.nova-lite-v1:0` (ใช้ cross-region inference profile), `--skip-preflight` (ข้ามการตรวจ)

<details>
<summary><b>ถ้าอยากสั่งเองทีละคำสั่ง (ไม่ใช้สคริปต์)</b></summary>

```bash
# 1. ตรวจความพร้อม (ต้องมี boto3 ของ python3.12 ถ้าเรียกด้วย python3.12)
python3.12 -m pip install --user boto3
python3.12 scripts/preflight.py

# 2. รวบรวมโค้ดและติดตั้งไลบรารีลง .aws-sam/build
sam build -t template.learner-lab.yaml

# 3. ติดตั้งขึ้น AWS — ต้องชี้ template ที่ build แล้วเท่านั้น
sam deploy \
  -t .aws-sam/build/template.yaml \
  --stack-name ai-equity-copilot \
  --region us-east-1 \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides AlertEmail=you@example.com BedrockModelId=amazon.nova-lite-v1:0
```

> ถ้าใส่ `-t template.learner-lab.yaml` (ไฟล์ต้นฉบับ) SAM จะแพ็กแค่ `src/` โดยไม่มี `fastapi`/`pandas` → Lambda ขึ้น `ImportError`

</details>

## ขั้นตอนที่ 3: ยืนยันอีเมลและเปิดใช้งานหน้าเว็บ

1. **กดยืนยันอีเมล SNS:** เปิดกล่องจดหมายอีเมลของคุณ (รวมถึงโฟลเดอร์ Spam/Junk) มองหาหัวข้อ **AWS Notification - Subscription Confirmation** แล้วคลิก **Confirm subscription**
2. **เข้าหน้าเว็บ Dashboard:** คัดลอกลิงก์จากตารางผลลัพธ์ช่อง **DashboardUrl** (ลงท้ายด้วย `.lambda-url.us-east-1.on.aws/`) ไปเปิดบนเบราว์เซอร์เพื่อเริ่มใช้งานได้ทันที

---

## วิธีลบทรัพยากรทั้งหมดหลังทดสอบเสร็จ (Cleanup)

```bash
cd /tmp/aws-financial && bash scripts/deploy_learnerlab.sh --delete
rm -rf /tmp/aws-financial /tmp/pip-cache
```

---

## ถ้าติดปัญหา

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| `ExpiredToken` / `InvalidClientTokenId` | Start Lab ใหม่ (session 4 ชม.) แล้วปิด CloudShell แล้วเปิดใหม่ |
| `Cannot find binary python3.12` ตอน build | ยังไม่ได้ติดตั้ง Python 3.12 ในขั้นตอนที่ 1 หรือ PATH ยังไม่เห็น → เปิด CloudShell ใหม่แล้วรันสคริปต์ซ้ำ |
| `Lambda ขึ้น ImportError: fastapi` | deploy ด้วย template ต้นฉบับ → build ใหม่แล้ว deploy ด้วย `.aws-sam/build/template.yaml` |
| `No space left on device` | ยังทำงานใน home directory → ต้องอยู่ใต้ `/tmp` ตามขั้นตอนที่ 1 |
| preflight ❌ Bedrock | แล็บบล็อกสิทธิ์ — ใช้ `--skip-preflight` แล้วเดโมด้วย rule-based fallback |
