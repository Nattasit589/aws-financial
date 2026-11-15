# QUICKSTART — ให้กลุ่มอื่นทำตาม (GitHub → AWS)

เป้าหมาย: จาก `git clone` ถึงหน้าเว็บใช้งานได้จริง **ภายใน ~10 นาที** โดยไม่ต้องติดตั้งอะไรในเครื่องเลย

> ใช้กับ **AWS Academy Learner Lab** (region `us-east-1`) เท่านั้น — ถ้าใช้บัญชี AWS ปกติให้อ่าน [SETUP_GUIDE.md](SETUP_GUIDE.md)

---

## สิ่งที่ต้องมี

- บัญชี AWS Academy ที่ลงทะเบียน Learner Lab แล้ว
- เบราว์เซอร์ 1 ตัว (ไม่ต้องลง Docker / Python / AWS CLI ในเครื่อง)

---

## 4 ขั้นตอน

### 1) Start Lab

เข้า AWS Academy → Learner Lab → กด **Start Lab** → รอจุดสถานะเป็น **สีเขียว**

### 2) เปิด CloudShell แล้ว clone โค้ด

ในหน้า AWS Console (region `us-east-1`) กดไอคอน **CloudShell** (`>_`) ที่แถบด้านบน
CloudShell ถูก authenticate กับบัญชีเดียวกับที่คุณล็อกอินอยู่แล้ว **ไม่ต้องรัน `aws configure`**

```bash
git clone https://github.com/Nattasit589/aws-financial.git
cd aws-financial
```

### 3) รันสคริปต์เดียวจบ

```bash
bash scripts/deploy_learnerlab.sh --email you@example.com
```

สคริปต์จะทำให้ทั้งหมดนี้:
1. ตรวจ credential / LabRole
2. ตรวจ `sam` (ถ้าไม่มีจะติดตั้งให้ใน CloudShell)
3. เลือกวิธี build ที่ถูกต้อง (ใช้ Python 3.12 ถ้ามี หรือ Docker ถ้ามี)
4. รัน preflight ตรวจสิทธิ์ Bedrock + บริการที่ต้องใช้
5. `sam build` + `sam deploy` แบบไม่ต้องตอบคำถาม
6. พิมพ์ `DashboardUrl` ให้เปิดใช้งาน

> ไม่ต้องการอีเมล: `bash scripts/deploy_learnerlab.sh`
> เปลี่ยนชื่อ stack: เพิ่ม `--stack my-group`
> ข้ามการตรวจ preflight: `--skip-preflight`

### 4) เปิด DashboardUrl

คัดลอกลิงก์ที่สคริปต์พิมพ์ตอนท้าย (หรือดูใน CloudFormation → Outputs) เปิดในเบราว์เซอร์ แล้ว:
1. พิมพ์ Workspace Code ของกลุ่ม เช่น `GROUP7-DEMO` → **โหลดพอร์ต**
2. เพิ่ม `PTT.BK`, `ADVANC.BK`, `NVDA` → **วิเคราะห์พอร์ตด้วย AI**
3. ถ้ากรอกอีเมล: ไปกด **Confirm subscription** ในกล่องจดหมายก่อน แล้วค่อยกด **ส่งรายงานเข้าอีเมล (SNS)**

---

## ถ้าติดปัญหา

| อาการ | วิธีแก้ |
|---|---|
| `ExpiredToken` / `InvalidClientTokenId` | Start Lab ใหม่ (session 4 ชม.) แล้วปิด CloudShell แล้วเปิดใหม่ |
| `ไม่พบ aws CLI` | ใช้ CloudShell เท่านั้น (ไม่ใช่ cmd/PowerShell) |
| `ต้องมี Python 3.12 หรือ Docker เพื่อ build` | ใช้ CloudShell (มักมี 3.12) หรือสลับไป build บนเครื่องตัวเองตาม [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md) |
| `not authorized to perform: iam:CreateRole` | สคริปต์ใช้ `template.learner-lab.yaml` + `LabRole` อยู่แล้ว — ตรวจว่าได้ clone เวอร์ชันล่าสุด (`git pull`) |
| Bedrock ขึ้น ❌ ใน preflight | แอปยังใช้ได้ (fallback) — แจ้งอาจารย์ขอเปิดสิทธิ์ หรือลอง `--model us.amazon.nova-lite-v1:0` |
| CloudShell หลุด/ปิดเอง | เปิดใหม่แล้ว `cd aws-financial` ต่อได้เลย (ไฟล์ยังอยู่) |

---

## ลบของเมื่อเลิกใช้

```bash
sam delete --stack-name ai-equity-copilot --region us-east-1
```

หรือ `bash scripts/deploy_learnerlab.sh --delete`

---

## หมายเหตุสำหรับผู้ทำตาม

- CloudShell มีพื้นที่ ~1 GB และ session หลุดเมื่ออยู่เฉย ~20 นาที — build ครั้งแรกใช้ 3–8 นาที
- ข้อมูลพอร์ตแยกตาม Workspace Code จึงไม่ชนกับกลุ่มอื่น แต่**ทุกกลุ่มใช้ stack คนละชื่อ**เพื่อไม่ทับกัน (ใช้ `--stack group7` เป็นต้น)
- รายละเอียดเชิงลึก (Bedrock, EventBridge, การเดโม) อยู่ใน [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md)
