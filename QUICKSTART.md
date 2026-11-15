# ⚡ Quickstart — ติดตั้งใน AWS CloudShell (AWS Academy Learner Lab)

คู่มือฉบับรัดกุมสำหรับติดตั้งระบบ **AI Equity Co-Pilot** บน **AWS CloudShell** (Region: us-east-1) โดยไม่ต้องใช้ Docker และไม่ติดปัญหาพื้นที่ 1 GB ของ CloudShell เต็ม

---

## ขั้นตอนที่ 1: เตรียมสภาพแวดล้อมและ Clone โปรเจกต์ใน /tmp

เปิด **AWS Console** จากหน้า Learner Lab (ตรวจสอบว่าอยู่มุมขวาบนที่ Region **us-east-1**) กดไอคอน **CloudShell** แล้วก๊อปปี้ชุดคำสั่งนี้วางรันได้เลย:

```bash
# 1. ติดตั้ง Python 3.12 เพื่อสั่ง Build แบบรวดเร็วโดยไม่ต้องพึ่ง Docker
sudo dnf install -y python3.12 python3.12-pip

# 2. ย้ายไปทำงานใน /tmp (มีพื้นที่ว่าง ~10 GB ป้องกันปัญหาพื้นที่โฮม 1 GB เต็ม)
export TMPDIR=/tmp PIP_CACHE_DIR=/tmp/pip-cache
cd /tmp
git clone https://github.com/Nattasit589/aws-financial.git
cd aws-financial
```

## ขั้นตอนที่ 2: สั่ง Build และ Deploy ขึ้น AWS

เปลี่ยน `[อีเมลของคุณ]` เป็นอีเมลจริงที่เปิดเช็กข้อความได้ แล้วรันชุดคำสั่งนี้:

```bash
# 1. ตรวจสอบความพร้อมของบัญชี Learner Lab
python3.12 scripts/preflight.py

# 2. รวบรวมโค้ดและติดตั้งไลบรารีลงใน .aws-sam/build
sam build -t template.learner-lab.yaml

# 3. ติดตั้งระบบทั้งหมดขึ้น AWS (ใช้ไฟล์ Template ที่ผ่านการ Build แล้ว)
sam deploy \
  -t .aws-sam/build/template.yaml \
  --stack-name ai-equity-copilot \
  --region us-east-1 \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides AlertEmail=[อีเมลของคุณ] BedrockModelId=amazon.nova-lite-v1:0
```

> **หมายเหตุ:** หากในขั้นตอน Preflight แจ้งว่า Bedrock ถูกปฏิเสธสิทธิ์ (AccessDeniedException) ไม่ต้องกังวล ระบบจะสลับไปใช้โหมดวิเคราะห์สำรอง (Rule-based fallback) ให้อัตโนมัติและทำงานครบทุกฟีเจอร์

## ขั้นตอนที่ 3: ยืนยันอีเมลและเปิดใช้งานหน้าเว็บ

1. **กดยืนยันอีเมล SNS:** เปิดกล่องจดหมายอีเมลของคุณ (รวมถึงโฟลเดอร์ Spam/Junk) มองหาหัวข้อ **AWS Notification - Subscription Confirmation** แล้วคลิก **Confirm subscription**
2. **เข้าหน้าเว็บ Dashboard:** คัดลอกลิงก์จากตารางผลลัพธ์ช่อง **DashboardUrl** (ลงท้ายด้วย `.lambda-url.us-east-1.on.aws/`) ไปเปิดบนเบราว์เซอร์เพื่อเริ่มใช้งานได้ทันที

---

## วิธีลบทรัพยากรทั้งหมดหลังทดสอบเสร็จ (Cleanup)

```bash
sam delete --stack-name ai-equity-copilot --region us-east-1 --no-prompts
rm -rf /tmp/aws-financial /tmp/pip-cache
```
