# AI Equity Co-Pilot (Ultra-Lean AWS Serverless Edition)

แพลตฟอร์มผู้ช่วยวิเคราะห์หุ้นไทย (.BK) และหุ้นสหรัฐฯ อัตโนมัติด้วย Generative AI บนสถาปัตยกรรม **AWS Serverless 6 บริการหลัก** เปลี่ยนรายชื่อหุ้นในพอร์ตให้เป็น **AI Decision Dashboard** ภาษาไทยที่ปรับตามสไตล์นักลงทุน พร้อมคำนวณความเสี่ยงพอร์ตและแจ้งเตือนทางอีเมลอัตโนมัติ

> **รายวิชา:** CS446 / IT332 Cloud Computing Projects (มหาวิทยาลัยกรุงเทพ)
> **ทีมผู้พัฒนา:** [ระบุชื่อกลุ่มและรายชื่อสมาชิก 3-5 คน]

---

## ลิงก์สำหรับส่งงาน (Submission Links)

| # | รายการที่ต้องส่ง | ลิงก์ |
|---|---|---|
| 1 | **Source Code (Public Repository)** | [github.com/Nattasit589/aws-financial](https://github.com/Nattasit589/aws-financial) |
| 2 | **Step-by-Step Documentation** | [QUICKSTART.md](QUICKSTART.md) · [ฉบับ PDF (ภาพหน้าจอ)](Doc_Quickstart.pdf) |
| 3 | **AWS Architecture Diagram** | [architecture-diagram.png](architecture-diagram.png) |
| 4 | **Video / Vlog Implementation** | https://drive.google.com/file/d/1T84E9_ZCv16tBTPRULlVBdHW66ge9Pjh/view?usp=sharing |

> ทุกลิงก์เป็นการเปิดจาก repo **public** นี้โดยตรง ไม่ต้องล็อกอิน และไม่ต้องดาวน์โหลดไฟล์
>
> **คู่มือฉบับอื่น (สำหรับกลุ่มที่ใช้บัญชีต่างกัน):** [QUICKSTART.md](QUICKSTART.md) ฉบับย่อ 3 คำสั่งบน CloudShell · [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md) ฉบับละเอียดสำหรับ AWS Academy Learner Lab · [SETUP_GUIDE.md](SETUP_GUIDE.md) บัญชี AWS ปกติ · [MANUAL_CONSOLE_SETUP.md](MANUAL_CONSOLE_SETUP.md) ทำมือทีละคลิกใน Console · [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) เช็กลิสต์ซ้อมเดโม 10 นาที

---

## Project Description & Architecture Summary (คำอธิบายโปรเจกต์และสรุปสถาปัตยกรรม)

**Project Description:** AI Equity Co-Pilot คือเว็บแอปพลิเคชันภาษาไทยสำหรับนักลงทุนรายย่อยที่ต้องการวิเคราะห์พอร์ตหุ้นไทย (.BK) และหุ้นสหรัฐฯ โดยไม่ต้องนั่งอ่านกราฟและข่าวทีละตัว ผู้ใช้สร้าง “พอร์ต” ของตัวเองด้วยรหัส Workspace Code เพิ่ม/ลบหุ้นใน watchlist เลือกสไตล์การลงทุน (สายปันผล หรือสายเก็งกำไรระยะสั้น) แล้วกดวิเคราะห์ครั้งเดียว ระบบจะดึงราคาย้อนหลัง 1 ปี ข่าวล่าสุด และข้อมูลพื้นฐานของทุกหุ้นแบบขนาน แล้วให้ AI สรุปเป็น **AI Decision Dashboard**: คะแนน 0–100, สัญญาณ BUY/WATCH/SELL, ระดับความเสี่ยงพร้อมเหตุผล, จุดเข้าซื้อ/ตัดขาดทุน/เป้าทำกำไร, ปัจจัยหนุน–ปัจจัยกดดัน (bull/bear), อารมณ์ข่าว และ **Greed & Fear Index 0–100** ที่บอกว่าตลาดและพอร์ตกำลังกลัวหรือโลภ นอกจากนี้ระบบยังวิเคราะห์ทุกพอร์ตอัตโนมัติทุกวันทำการหลังตลาดหุ้นไทยปิด (17:15 น.) แล้วส่งรายงานสรุปเข้าอีเมลผ่าน Amazon SNS พร้อมเก็บสำเนารายงานเป็น JSON ไว้บน Amazon S3

**Architecture Summary (สรุปสถาปัตยกรรม):** ทั้งระบบรันแบบ **AWS Serverless 100%** ไม่มีเซิร์ฟเวอร์ให้ดูแล และใช้ 6 บริการหลัก:

```text
ผู้ใช้ (เบราว์เซอร์)
   │  HTTPS
   ▼
AWS Lambda  ── FastAPI ผ่าน Mangum + Lambda Function URL (เสิร์ฟทั้งหน้าเว็บและ REST API)
   ├──► Amazon DynamoDB   watchlist ต่อ Workspace + Smart Cache ผลวิเคราะห์ล่าสุด (TTL)
   ├──► Amazon S3         สำเนารายงาน JSON (reports/<workspace>/<วันที่>/<manual|scheduled>.json)
   ├──► Amazon SNS        อีเมลรายงานสรุป (ผู้รับต้องกด Confirm subscription)
   ├──► Amazon Bedrock    วิเคราะห์ด้วย AI → ถ้าถูกบล็อกสิทธิ์จะใช้ Google Gemini → สุดท้ายคือกฎเทคนิค
   └──► แหล่งข้อมูลภายนอก  yfinance (ราคา+ข่าว) และ Google News RSS (ไม่ใช่บริการ AWS)
   ▲
   │  cron(15 10 ? * MON-FRI *) = 17:15 น. เวลาไทย
Amazon EventBridge (ปลุก Lambda วิเคราะห์ทุกพอร์ตอัตโนมัติ)
```

**การไหลของข้อมูล (Data Flow):**
1. **คำขอบทวิเคราะห์ (on-demand):** เบราว์เซอร์ → Function URL → Lambda ดึงราคา/ข่าวแบบขนาน → Bedrock สรุปเป็น JSON → เขียนผลลง DynamoDB (Smart Cache) → ตอบกลับหน้าเว็บพร้อม Greed & Fear Index
2. **งานอัตโนมัติ (scheduled):** EventBridge ปลุก Lambda วันจันทร์–ศุกร์ 17:15 น. → อ่าน Workspace ทั้งหมดจาก DynamoDB → วิเคราะห์ใหม่แบบบังคับดึงสด (ไม่ใช้ cache เก่าก่อนตลาดปิด) → เก็บสำเนา JSON ลง S3 → ส่งอีเมลสรุปรวมทุกพอร์ตผ่าน SNS
3. **เมื่อ AI หลักใช้งานไม่ได้:** Bedrock error/timeout → ลอง Gemini (ถ้ามี key) → ตกไปกฎเทคนิค โดยการ์ดผลลัพธ์ระบุที่มาเสมอ (`Bedrock AI` / `Gemini · AI สำรอง` / `กฎเทคนิค · ไม่ใช่ AI`) — ระบบต้องไม่ล่ม (ไม่คืน 500)

**เหตุผลการออกแบบที่สำคัญ:** ใช้ Lambda Function URL แทน API Gateway (ลดบริการและเลี่ยงเพดาน timeout 29 วินาที), ใช้ `Mangum` ให้ FastAPI ทำงานบน Lambda ได้โดยไม่ต้องเขียน HTTP layer เอง, ใช้ S3 สำหรับ**เก็บสำเนารายงานเท่านั้น** (ไม่ใช้ static hosting), และเลือกใช้ `LabRole` ที่มีอยู่แล้วใน AWS Academy Learner Lab แทนการสร้าง IAM role ใหม่ — ตารางบริการและสิทธิ์แบบละเอียดอยู่ในหัวข้อถัดไป

---

## ประโยชน์ของแอปพลิเคชันและโมเดลธุรกิจ (Application Benefit & Level 5 Viability)

- **แก้ปัญหาจริงของนักลงทุนรายย่อย:** ลดเวลาอ่านข่าวและดูกราฟหุ้นหลายตัว ด้วยบทสรุปคะแนน (0–100), สัญญาณ (Buy / Watch / Sell), จุดเข้าซื้อ-ตัดขาดทุน และปัจจัยเสี่ยงภาษาไทย
- **แยกพอร์ตหลายผู้ใช้งาน (Multi-Workspace):** รองรับการสร้างและสลับพอร์ตแยกตามรหัสพอร์ต (Workspace Code) โดยข้อมูลไม่ปนกัน
- **ปรับคำแนะนำตามสไตล์นักลงทุน (Investor Persona):** เลือกโหมดวิเคราะห์ได้ทั้ง **สายปันผลเน้นปลอดภัย (Conservative Dividend)** และ **สายเก็งกำไรระยะสั้น (Short-Term Momentum)**
- **สรุปภาพรวมรายตัวแบบ Decision Dashboard:** ตารางย่อ (สัญญาณ · คะแนน · เปลี่ยนแปลง · ระดับความเสี่ยง) ช่วยให้ตัดสินใจได้ในหน้าเดียว พร้อมป้ายความเสี่ยงต่ำ/กลาง/สูง และอารมณ์ข่าว (บวก/กลาง/ลบ)
- **Greed & Fear Index (คำนวณเอง 7 องค์ประกอบ):** ดัชนี 0–100 บอกว่าตลาดและพอร์ตกำลัง "กลัว" หรือ "โลภ" จาก VIX, โมเมนตัมดัชนีตลาด (S&P 500 / SET เทียบ SMA50), ความกว้างของตลาดในพอร์ต, RSI เฉลี่ย, ตำแหน่งราคาเทียบจุดสูงสุด 52 สัปดาห์, อารมณ์ข่าว และสัดส่วนสัญญาณ AI — แสดงบนหน้าเว็บพร้อมกราฟ 30 วัน และแนบไปในอีเมลรายงาน (ทนต่อข้อมูลที่ขาดด้วยการถ่วงน้ำหนักใหม่ และถ้าพอร์ตมีหุ้นน้อยกว่า 3 ตัวจะใช้เฉพาะข้อมูลตลาด) โดยไม่เพิ่ม AWS service หรือ dependency ใด ๆ
- **ศักยภาพเชิงพาณิชย์ (Unit Economics):** ต้นทุน AI ต่อหุ้นที่แสดงในหน้าเว็บเป็น**ค่าประมาณจากตารางราคา token** ของแต่ละโมเดล (ไม่ใช่บิลจริง) ใช้ประกอบการตั้งราคาบริการ SaaS รายเดือน (เช่น 199 บาท/เดือน) และคำนวณจุดคุ้มทุน/อัตรากำไรขั้นต้นได้จาก Business & Cost Calculator ในหน้าเว็บ

---

## สถาปัตยกรรมระบบบน AWS (6 Core AWS Services)

โปรเจกต์นี้ใช้งานได้ครบทุกฟีเจอร์โดย**ไม่ต้องสมัครคีย์เว็บนอก** และมีตัวเลือกใส่ **Gemini API key** (จาก Google AI Studio) เป็น AI สำรองเมื่อ Bedrock เรียกไม่ได้ — ลำดับการเลือก AI คือ **Bedrock → Gemini → กฎเทคนิค** โดยใช้บริการหลักของ AWS จำนวน **6 บริการ** (ไม่นับรวมบริการจัดการพื้นฐานสีม่วงตามเกณฑ์รายวิชา ได้แก่ IAM, VPC, CloudWatch, CLI และ Cost & Usage Report) — ในจำนวนนี้ **5 บริการอยู่ในลิสต์สไลด์รายวิชา** (Lambda, DynamoDB, S3, EventBridge, SNS) ส่วน Bedrock เป็น AI layer สำหรับฟีเจอร์ Generative AI

| ลำดับ | บริการ AWS | หน้าที่หลักในระบบ |
|---|---|---|
| 1 | **AWS Lambda (Function URL)** | รันระบบหลังบ้าน FastAPI เสิร์ฟหน้าเว็บ Dashboard และประมวลผลหุ้นแบบขนาน (Parallel) |
| 2 | **Amazon DynamoDB** | จัดเก็บรายชื่อหุ้นแยกตามพอร์ต (CRUD) และผลวิเคราะห์**ล่าสุด**ต่อหุ้น+โหมดแบบ Smart Cache (TTL ทับผลเดิม ไม่ใช่ประวัติย้อนหลัง) |
| 3 | **Amazon S3** | เก็บ**สำเนารายงาน**ที่ส่งออกทุกรอบเป็น JSON (`reports/<พอร์ต>/<วันที่>/<manual\|scheduled>.json`) ไว้เปิดดู/ดึงย้อนหลังได้ด้วย S3 Object URL — ลิงก์ `s3://...` ถูกแนบไปในอีเมลและตอบกลับใน API ด้วย |
| 4 | **Amazon Bedrock** | ประมวลผลตัวเลขเทคนิคและข่าวสารด้วยโมเดล AI เพื่อสร้างแผนเทรดภาษาไทย |
| 5 | **Amazon EventBridge** | ตั้งเวลาปลุก AWS Lambda มาวิเคราะห์หุ้นทุกพอร์ตอัตโนมัติในวันทำการหลังตลาดปิด |
| 6 | **Amazon SNS** | ส่งอีเมลรายงานสรุปอัตโนมัติทุกวันทำการหลังตลาดปิด (รวมทุกพอร์ตในอีเมลเดียว ถึงผู้รับที่สมัครกับ topic) |

> S3 bucket สร้างโดย stack เอง (ชื่อสุ่ม ดูได้จาก Output `ReportBucketName`) ตั้ง Block Public Access + เข้ารหัส AES256 และลบสำเนารายงานอัตโนมัติใน 30 วัน — ไม่ได้ใช้ทำ static hosting

*(หมายเหตุ: แผนผังสถาปัตยกรรมในสไลด์นำเสนออ้างอิงไอคอนมาตรฐานจาก aws-icons.com)*

### ความเข้ากันได้กับ AWS Academy Learner Lab

โปรเจกต์นี้รันได้ทั้งบนบัญชี AWS ปกติและบน **AWS Academy Learner Lab** (region `us-east-1` / `us-west-2`) โดยใช้ `template.learner-lab.yaml` แทน `template.yaml` เพราะ Learner Lab **ไม่อนุญาตให้สร้าง IAM role** จึงต้องผูก role ที่มีอยู่แล้วชื่อ `LabRole` แทน

ก่อน deploy ให้รัน `python scripts/preflight.py` เพื่อตรวจ credential, IAM role (`LabRole`) และ trust policy, CloudFormation, S3, Lambda, DynamoDB, SNS, EventBridge, CloudWatch Logs, Function URL และทดสอบเรียก Bedrock จริง 1 ครั้ง (ผล Bedrock ไม่บล็อกการ deploy เพราะระบบมี AI สำรอง)

**คู่มือแยกตามประเภทบัญชี:**
- ⚡ **กลุ่มอื่นที่ต้องการ clone แล้วติดตั้งด้วยชุดคำสั่งเดียว: [QUICKSTART.md](QUICKSTART.md)** (CloudShell, ไม่ต้องลงอะไรในเครื่อง) · [ฉบับ PDF](Doc_Quickstart.pdf)
- 🎓 **AWS Academy Learner Lab (เส้นทางหลักของรายวิชา): [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md)**
- ☁️ บัญชี AWS ปกติ: [SETUP_GUIDE.md](SETUP_GUIDE.md)

---

## คู่มือการติดตั้งและรันระบบ (Step-by-Step Reproduction Guide)

> คู่มือแยกตามผู้ใช้:
> - **กลุ่มอื่นทำตามเร็วๆ → [QUICKSTART.md](QUICKSTART.md)** (clone + CloudShell + สคริปต์เดียวจบ)
> - **AWS Academy Learner Lab (ละเอียด) → [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md)**
> - บัญชี AWS ปกติ → [SETUP_GUIDE.md](SETUP_GUIDE.md)

คู่มือนี้ออกแบบให้กลุ่มผู้ทดสอบติดตั้งระบบทั้งหมดขึ้นบัญชี AWS ของตนเองจนใช้งานได้จริง โดยไม่ต้องสมัคร API key ภายนอก (Gemini key เป็นตัวเลือกเสริม)

### สิ่งที่ต้องเตรียมล่วงหน้า (Prerequisites)
- บัญชี AWS ที่พร้อมใช้งาน (แนะนำ Region: `us-east-1` — ใช้ได้ทั้งบัญชีปกติและ AWS Academy Learner Lab)
- ติดตั้ง **AWS CLI** และตั้งค่าสิทธิ์ผ่านคำสั่ง `aws configure` เรียบร้อยแล้ว
- ติดตั้ง **AWS SAM CLI** และ **Python 3.12** (หรือ Docker สำหรับช่วย Build แพ็กเกจ)
- ถ้าใช้ **AWS Academy Learner Lab:** ต้องกด Start Lab ทุก session และคัดลอก credential ใหม่ พร้อมใช้ `template.learner-lab.yaml` (รายละเอียดใน [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md))

### ขั้นตอนที่ 1: ตรวจสิทธิ์ใช้งานโมเดล AI บน Amazon Bedrock
ในบัญชี AWS ปกติ โมเดลส่วนใหญ่เปิดใช้ได้ทันทีเมื่อเรียกครั้งแรก (ไม่ต้องกดขอสิทธิ์ที่หน้า Model access แบบเดิมแล้ว) แต่ถ้าเรียกแล้วได้ `AccessDeniedException` ให้ตรวจตามลำดับนี้:
1. เข้า **AWS Console** → เลือก Region `us-east-1`
2. เปิด **Amazon Bedrock** → ทดสอบใน **Playground** ด้วยโมเดล `amazon.nova-lite-v1:0`
3. ถ้าเรียกผ่าน CLI ให้รัน `python scripts/preflight.py` (สคริปต์จะทดสอบเรียกโมเดลจริง 1 ครั้งและบอกผลชัดเจน)
4. ถ้าใช้ **Learner Lab** แล้ว Bedrock ถูกบล็อก: แอปยังใช้งานได้ครบ โดยจะลอง **Gemini** เป็น AI สำรองก่อน (ถ้าตั้งค่า `GeminiApiKey` ไว้) แล้วจึงตกไปกฎเทคนิค — ป้ายบนการ์ดระบุที่มาเสมอ (**Bedrock AI** / **Gemini · AI สำรอง** / **กฎเทคนิค · ไม่ใช่ AI**) ควรแจ้งอาจารย์หรือผู้ดูแลแล็บ

### ขั้นตอนที่ 2: ติดตั้งระบบทั้งหมดด้วยคำสั่งเดียว (AWS SAM Deploy)

> **เส้นทางที่ทดสอบแล้วบน AWS Academy Learner Lab (CloudShell):** ทำตาม [QUICKSTART.md](QUICKSTART.md) — รัน `bash scripts/deploy_learnerlab.sh` แล้วสคริปต์จะตรวจสิทธิ์ build และ deploy ให้ทั้งหมด พร้อมถามอีเมล/Gemini key
> คำสั่งด้านล่างเป็นทางเลือกสำหรับทำเองทีละขั้น

เปิด Terminal ในโฟลเดอร์โปรเจกต์ แล้วรันคำสั่งต่อไปนี้ตามลำดับ:

```bash
# 1. ดาวน์โหลดไลบรารีและเตรียมแพ็กเกจสำหรับ AWS Lambda
sam build

# 2. ติดตั้งขึ้นระบบ AWS แบบมีตัวช่วยถามค่าเริ่มต้น
sam deploy --guided
```

> **หมายเหตุ:** หาก build บน Windows หรือ macOS ให้ใช้ `sam build --use-container` เพื่อให้ไลบรารีที่มี binary (pandas/numpy จาก yfinance) ถูก build ให้ตรงกับสภาพแวดล้อม Linux ของ AWS Lambda

> **ถ้าใช้ AWS Academy Learner Lab:** ใช้ไฟล์ template ของ Learner Lab และตอบ `N` ที่คำถาม Allow SAM CLI IAM role creation
>
> ```bash
> sam build -t template.learner-lab.yaml
> sam deploy --guided -t .aws-sam/build/template.yaml
> ```
>
> **สำคัญ:** ตอน deploy ต้องชี้ template ที่ build แล้ว (`.aws-sam/build/template.yaml`) เท่านั้น — ถ้าชี้ไฟล์ต้นฉบับ SAM จะแพ็กแค่ `src/` โดยไม่มีไลบรารี ทำให้ Lambda ขึ้น `ImportError` (บน CloudShell ที่ติดตั้ง Python 3.12 แล้ว build ตรงๆ ได้ ไม่ต้องใช้ `--use-container`)

ในขั้นตอน `sam deploy --guided` ให้กรอกค่าดังนี้:
- **Stack Name:** `ai-equity-copilot`
- **AWS Region:** `us-east-1` (หรือ Region เดียวกับที่เช็ก Bedrock ในขั้นตอนที่ 1)
- **Parameter AlertEmail:** กรอกอีเมลจริงของคุณเพื่อใช้ทดสอบรับการแจ้งเตือนจาก Amazon SNS
- **Parameter BedrockModelId:** กด Enter เพื่อใช้ค่าเริ่มต้น (หรือระบุ Model ID ที่เปิดไว้)
- **Parameter GeminiApiKey:** เว้นว่างได้ — ถ้าใส่ จะใช้เป็น AI สำรองเมื่อ Bedrock เรียกไม่ได้
- **Confirm changes before deploy:** `N`
- **Disable rollback:** `N`
- **StockCopilotFunction (หรือ StockCopilotFunctionUrl) has no authentication. Is this okay?:** พิมพ์ `y` แล้วกด Enter (เพื่อให้เปิดเข้าหน้าเว็บผ่าน Function URL ได้)
- **Allow SAM CLI IAM role creation:** `Y` สำหรับบัญชีปกติ — **แต่ถ้าใช้ Learner Lab ให้ตอบ `N`** (Learner Lab สร้าง IAM role ไม่ได้)
- **Save arguments to configuration file:** `Y`

### ขั้นตอนที่ 3: ยืนยันอีเมล SNS และเข้าใช้งานหน้าเว็บจริง
1. **ยืนยันอีเมลแจ้งเตือน:** เปิดกล่องจดหมายอีเมลที่คุณกรอกไว้ มองหาอีเมลหัวข้อ `AWS Notification - Subscription Confirmation` แล้วคลิกปุ่ม **Confirm subscription**
2. **เปิดหน้าเว็บ Dashboard:** เมื่อ Terminal ติดตั้งเสร็จ ให้คัดลอกลิงก์จากหัวข้อ **Outputs -> DashboardUrl** (รูปแบบ `https://xxxxxxxx.lambda-url.us-east-1.on.aws/`) ไปเปิดบนเบราว์เซอร์ได้ทันที
3. **ทดสอบระบบครบวงจร:**
   - พิมพ์ชื่อพอร์ตของคุณในช่อง **Workspace Code** (เช่น `TEST-GROUP1`) แล้วกดโหลดพอร์ต
   - เพิ่มชื่อหุ้นไทย (เช่น `PTT.BK`, `ADVANC.BK`) หรือหุ้นสหรัฐฯ (เช่น `NVDA`, `AAPL`)
   - เลือกโหมดนักลงทุน แล้วกดปุ่ม **วิเคราะห์พอร์ต** เพื่อดูผลลัพธ์สด
   - กดปุ่ม **ส่งรายงานเข้าอีเมล** เพื่อตรวจสอบว่าได้รับอีเมลสรุปผลเข้ากล่องจดหมายจริง

### วิธีลบทรัพยากรทั้งหมดหลังทดสอบเสร็จ (Cleanup)
เพื่อป้องกันค่าใช้จ่ายตกค้างหลังจบการประเมิน สามารถลบทุกบริการทิ้งได้ด้วยคำสั่งเดียว:

```bash
sam delete --stack-name ai-equity-copilot
```

### ทดสอบหน้าเว็บแบบออฟไลน์ (ไม่ต้อง deploy)

```bash
python scripts/preview_dashboard.py    # เสิร์ฟหน้าเว็บที่ http://127.0.0.1:8765 ด้วยข้อมูลสมมติ ไม่เรียก AWS/อีเมล
python scripts/test_regressions.py     # รันชุดทดสอบ regression ของ backend (ไม่ต้องมี credential)
```

---

## การเก็บโค้ดบน GitHub

แนะนำให้ push ทั้งโฟลเดอร์ขึ้น **private repo** เพื่อเก็บงานและให้เพื่อน clone ไปทำตามได้ แต่ควรรู้ไว้ 3 ข้อ:

1. **push ไม่ได้ทำให้ deploy ง่ายขึ้น** — SAM ยังรัน `sam build` / `sam deploy` จากเครื่องที่มี AWS CLI + credential (Learner Lab ต้อง Start Lab ทุกครั้ง)
2. **ห้าม commit**: `samconfig.toml` (มี stack name, region, อีเมล), `.aws-sam/`, `.env`, credential ทุกชนิด — `.gitignore` ในโปรเจกต์กันไว้ให้แล้ว
3. **ไม่ต้องตั้ง CI/CD auto-deploy** — GitHub Actions ที่ deploy ขึ้น AWS จะต้องสร้าง IAM role เพิ่ม ซึ่ง Learner Lab ทำไม่ได้ และจะทำให้จำนวนบริการเกิน 5 ตามข้อกำหนดรายวิชา

```bash
git init
git add .
git commit -m "AI Equity Co-Pilot: serverless AI stock dashboard"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

> ถ้าอัปโหลดผ่านหน้าเว็บ GitHub (ลากไฟล์) ไฟล์ `.gitignore` จะไม่ทำงาน — ต้องตรวจว่าไม่มี `samconfig.toml` หรือโฟลเดอร์ `.aws-sam` ติดไปด้วย

---

## ความสอดคล้องกับเกณฑ์การประเมินของรายวิชา (Level 4–5)

อ้างอิงเกณฑ์ใน `Final_Project.pdf` (หัวข้อ AWS Project Assessment และ Useful Applications Level)

| เกณฑ์ในโจทย์ | หลักฐานในโปรเจกต์นี้ | สถานะ |
|---|---|---|
| งานกลุ่ม 3–5 คน | โครงสร้างโปรเจกต์เดียว ไม่มี dependency ส่วนตัว | ⬜ ต้องเติมชื่อสมาชิก 3–5 คน |
| ใช้ AWS Services อย่างน้อย 4 บริการ (ไม่นับ Purple Service) | **Lambda, DynamoDB, S3, EventBridge, SNS = 5 บริการที่อยู่ในลิสต์สไลด์** (+ Bedrock เป็น AI layer = 6 บริการที่เรียกใช้จริง; IAM/CloudWatch/CLI ไม่นับตามเกณฑ์) | ✅ |
| Level 3: Complete Application (Web + Database) | CRUD Watchlist, Dashboard, DynamoDB single-table, multi-workspace | ✅ เกินLevel 3 |
| **Level 4:** Automated, Integrated System — 4+ บริการ + external data API + automated value | EventBridge cron ปลุก Lambda วิเคราะห์ทุกพอร์ตวันทำการ → ส่งอีเมล SNS อัตโนมัติ; ข้อมูลภายนอกจาก `yfinance` + Google News RSS; Bedrock สร้างแผนเทรดภาษาไทย | ✅ |
| Deliverable: วิดีโอ/vlog ขั้นตอน implementation | — | ⬜ ต้องอัดเอง |
| Deliverable: Documentation ที่กลุ่มอื่นทำตามได้ทันเวลา | [QUICKSTART.md](QUICKSTART.md) (CloudShell), [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md) (Learner Lab) และ [SETUP_GUIDE.md](SETUP_GUIDE.md) (AWS ปกติ) + `scripts/preflight.py` ตรวจความพร้อมก่อน deploy | ✅ |
| Demo day: ของจริง + Benefit + Architecture + Demonstration | หน้าเว็บทำงานจริง, ตารางสถาปัตยกรรม 6 บริการ, ตัวเลขต้นทุน token ประมาณการ | ✅ (ต้องทำสไลด์/แผนผังเอง) |
| **Level 5:** Commercially Viable — มีคนยอมจ่ายเงินใช้ | Unit economics คำนวณจากตารางราคา token (ประมาณการ), ต้นทุนต่อหุ้นแสดงในหน้าเว็บ, แพ็กเกจ 199 บาท/เดือน, จุดคุ้มทุนในหน้าเว็บ | ⚠️ โครงสร้างธุรกิจครบ แต่ยังขาดหลักฐานความต้องการจากตลาด |

### สิ่งที่ต้องทำเพิ่มเพื่อให้ถึง Level 5

1. **หลักฐานความต้องการ:** สำรวจ/สัมภาษณ์นักลงทุนรายย่อย 10–20 คน (แบบฟอร์ม + สรุปผล) ว่าเคยใช้เวลาวิเคราะห์หุ้นนานแค่ไหน และยอมจ่ายเท่าไร
2. **ราคาและต้นทุน:** ใช้ตัวเลขจาก **Business & Cost Calculator** ในหน้าเว็บ (ต้นทุน token ประมาณการ) ประกอบการตั้งราคา และแสดง Gross Margin ในสไลด์
3. **แผนธุรกิจสั้นๆ:** กลุ่มลูกค้าเป้าหมาย (นักลงทุนรายย่อย/อาจารย์สอนการเงิน), ช่องทางขาย, และแผนขยาย (แจ้งเตือน Line/Telegram, พอร์ตหลายตลาด)

### ข้อจำกัดที่ต้องรู้ก่อนเดโม

- บน **AWS Academy Learner Lab** สิทธิ์ Bedrock ขึ้นกับแล็บ: ถ้าเรียกไม่ผ่าน แอปยังทำงานครบทุกบริการ (เหลือ AI สำรอง + S3/SNS/EventBridge ทำงานปกติ) โดยผลวิเคราะห์จะมาจาก **Gemini** (ถ้าใส่ key ไว้) หรือ **กฎเทคนิค** — ป้ายบนการ์ดระบุที่มาชัดเจน ควรแจ้งอาจารย์ล่วงหน้า
- ข้อมูลราคา/ข่าวมาจาก `yfinance` และ Google News แบบไม่เป็นทางการ: อาจดีเลย์หรือถูกจำกัดอัตราการเรียกได้ในบางช่วง ถ้าดึงข้อมูลไม่ได้ ระบบจะแจ้งเป็นภาษาไทยรายหุ้น ไม่ทำให้ทั้งพอร์ตล่ม

---

## การอ้างอิงแหล่งที่มา (Open-Source Attribution)
โปรเจกต์นี้ได้รับแรงบันดาลใจด้านโครงสร้างรายงาน AI Decision Dashboard และการคำนวณตัวชี้วัดทางเทคนิคจากโปรเจกต์ Open-source [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) (ภายใต้สัญญาอนุญาต **MIT License**) โดยทีมผู้พัฒนาได้ออกแบบสถาปัตยกรรมใหม่ทั้งหมดสำหรับรันแบบ Serverless บน AWS 6 บริการ

**สิ่งที่นำแนวคิดมาปรับใช้ (ไม่ใช่การคัดลอกโค้ด):** รูปแบบสรุปภาพรวมรายตัวแบบ decision dashboard (สัญญาณ/คะแนน/เปลี่ยนแปลง), แนวคิด `news_tone` และ `risk_level` ที่ทำให้ผู้ใช้เห็นความเสี่ยงก่อนตัดสินใจ และแนวคิดการลดจำนวน request ต่อหุ้น (ใช้ `history_metadata` แทน `ticker.info`, ยิงข่าวขนานกับการดึงราคา) ซึ่งลดเวลาต่อหุ้นจาก ~479 ms เหลือ ~269 ms ในการวัดบนเครื่องพัฒนา

**สิ่งที่ต่างจากต้นทางโดยตั้งใจ:** โปรเจกต์นี้ไม่บังคับใช้ API key ภายนอก (Gemini key เป็นตัวเลือกเสริม) ไม่พึ่งพาไลบรารีหนักเพิ่มเติม และใช้ AWS service เท่าที่จำเป็น (ไม่นับบริการจัดการพื้นฐานตามเกณฑ์รายวิชา) เพิ่มระบบแยกพอร์ตผู้ใช้งาน รองรับตลาดหุ้นไทย (.BK) ปรับโมเดลวิเคราะห์ตามสไตล์นักลงทุน และเชื่อมต่อ Amazon Bedrock โดยตรง
