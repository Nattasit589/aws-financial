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

วางคำสั่งเดียวนี้แล้วกด Enter — **ไม่ต้องแก้ข้อความในคำสั่ง** สคริปต์จะถามค่าที่ต้องใช้ให้กรอกทีละบรรทัด:

```bash
bash scripts/deploy_learnerlab.sh
```

สคริปต์จะถาม 2 อย่าง:

| ถามว่า | ให้พิมพ์ |
|---|---|
| `อีเมลรับแจ้งเตือน SNS (เว้นว่างได้):` | อีเมลจริง เช่น `name@gmail.com` แล้วกด Enter |
| `Gemini API key (เว้นว่างได้):` | วาง key จาก [Google AI Studio](https://aistudio.google.com/apikey) — **ถ้ายังไม่มี ให้กด Enter ข้าม** |

### Gemini API key คืออะไร (AI สำรอง)

Learner Lab มักไม่ให้สิทธิ์ `bedrock:InvokeModel` ทำให้ระบบต้องสรุปด้วยกฎเทคนิค (ป้าย **Rule-based Fallback** สีเหลือง) ถ้าใส่ key นี้ ระบบจะเรียก **Gemini** เป็น AI สำรองก่อนตกไปกฎเทคนิค — ไม่ใส่ก็ใช้ระบบได้ครบทุกฟีเจอร์

- key จะถูกส่งเป็น **Parameter ของ CloudFormation** (`NoEcho: true`) แล้ว SAM ฉีดเป็น environment variable `GEMINI_API_KEY` ให้ Lambda — **ไม่มี key ใน git**
- **ไม่มีการเพิ่ม AWS service ใด ๆ** (ยังคง Lambda, DynamoDB, Bedrock, EventBridge, SNS = 5 บริการ)
- ไม่เพิ่ม dependency ใน `requirements.txt` (ใช้ `urllib` จาก standard library)
- ลำดับการเลือก AI: **Bedrock → Gemini → กฎเทคนิค**
- เปลี่ยนโมเดล Gemini ได้ที่ `GeminiModelId` ตอน `sam deploy` (ค่าเริ่มต้น `gemini-3.5-flash-lite`) — ไม่ต้องแก้โค้ด
- ⚠️ repo นี้เป็น public — ห้าม commit key หรือใส่ใน screenshot

สคริปต์จะทำให้ทั้งหมดนี้ในคำสั่งเดียว:

1. ตรวจ credential (ไม่ต้อง `aws configure` เพราะ CloudShell ล็อกอินอยู่แล้ว)
2. ตรวจ `sam` (ถ้าไม่มีจะติดตั้งให้)
3. เลือกวิธี build ที่ตรงกับ runtime `python3.12` (ใช้ Python 3.12 ที่เพิ่งติดตั้ง / Docker ถ้ามี)
4. ติดตั้ง `boto3` ถ้าจำเป็น แล้วรัน preflight ตรวจสิทธิ์ Bedrock + บริการที่ต้องใช้
5. `sam build` → `sam deploy` ด้วย `.aws-sam/build/template.yaml` (template ที่มีไลบรารีครบ) แบบไม่ต้องตอบคำถาม
6. ส่ง `GeminiApiKey` (ถ้ากรอก key ตอนสคริปต์ถาม) และพิมพ์ **DashboardUrl** ให้เปิดใช้งานทันที> **หมายเหตุ:** หาก preflight แจ้งว่า Bedrock ถูกปฏิเสธสิทธิ์ (`AccessDeniedException`) ไม่ต้องกังวล ระบบจะใช้ **AI สำรอง Google Gemini** ก่อน (เมื่อกรอก key ตอนสคริปต์ถาม) ถ้าไม่มี key จะสลับไปใช้ Rule-based fallback — ป้ายบนการ์ดระบุชัดเจนทุกกรณี และแอปทำงานครบทุกฟีเจอร์

ออปชันเสริม: `--stack my-group` (เปลี่ยนชื่อ stack), `--model us.amazon.nova-lite-v1:0` (ใช้ cross-region inference profile), `--gemini-key <key>` (AI สำรองจาก Google AI Studio), `--skip-preflight` (ข้ามการตรวจ)

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
  --parameter-overrides AlertEmail=you@example.com BedrockModelId=amazon.nova-lite-v1:0 GeminiApiKey=AIza...
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
| preflight ❌ Bedrock | แล็บบล็อกสิทธิ์ — ใช้ `--skip-preflight` แล้วใส่ `--gemini-key` เพื่อใช้ AI สำรอง (หรือเดโมด้วย rule-based fallback) |
| ขึ้นแค่ป้าย **Rule-based Fallback** ไม่ขึ้น **AI สำรอง (Gemini)** | ตอนสคริปต์ถาม `Gemini API key` ไม่ได้วาง key (หรือกด Enter ข้าม), key ไม่ถูกต้อง/หมดสิทธิ์ หรือยังไม่ได้กด “บังคับวิเคราะห์ใหม่” (ผลเก่ายังอยู่ใน Smart Cache) |
| สคริปต์ไม่ถามอีเมล/Gemini key | รันโดยไม่มี terminal จริง หรือส่งค่ามาแล้วผ่าน flag (`--email`, `--gemini-key`) / env (`ALERT_EMAIL`, `GEMINI_API_KEY`) — ใส่ flag ตรง ๆ ได้ตามหัวข้อออปชันเสริม |
