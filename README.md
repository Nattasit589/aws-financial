# AI Equity Co-Pilot (Ultra-Lean AWS Serverless Edition)

แพลตฟอร์มผู้ช่วยวิเคราะห์หุ้นไทย (.BK) และหุ้นสหรัฐฯ อัตโนมัติด้วย Generative AI บนสถาปัตยกรรม **AWS Serverless 5 บริการหลัก** เปลี่ยนรายชื่อหุ้นในพอร์ตให้เป็น **AI Decision Dashboard** ภาษาไทยที่ปรับตามสไตล์นักลงทุน พร้อมคำนวณความเสี่ยงพอร์ตและแจ้งเตือนทางอีเมลอัตโนมัติ

> **รายวิชา:** CS446 / IT332 Cloud Computing Projects (มหาวิทยาลัยกรุงเทพ)
> **ทีมผู้พัฒนา:** [ระบุชื่อกลุ่มและรายชื่อสมาชิก 3-5 คน]

---

## ลิงก์สำหรับส่งงาน (Submission Links)

| # | รายการที่ต้องส่ง | ลิงก์ |
|---|---|---|
| 1 | **Source Code (Public Repository)** | `https://github.com/Nattasit589/aws-financial` |
| 2 | **Step-by-Step Documentation** | `https://github.com/Nattasit589/aws-financial/blob/main/QUICKSTART.md` |
| 3 | **AWS Architecture Diagram** | `https://github.com/Nattasit589/aws-financial/blob/main/architecture-diagram.png` |
| 4 | **Video / Vlog Implementation** | ⬜ *รอใส่ลิงก์วิดีโอ (YouTube / Google Drive แบบเปิดสาธารณะ)* |

> ทุกลิงก์เป็นการเปิดจาก repo **public** นี้โดยตรง ไม่ต้องล็อกอิน และไม่ต้องดาวน์โหลดไฟล์
>
> **คู่มือฉบับอื่น (สำหรับกลุ่มที่ใช้บัญชีต่างกัน):** [QUICKSTART.md](QUICKSTART.md) ฉบับย่อ 3 คำสั่งบน CloudShell · [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md) ฉบับละเอียดสำหรับ AWS Academy Learner Lab · [SETUP_GUIDE.md](SETUP_GUIDE.md) บัญชี AWS ปกติ · [MANUAL_CONSOLE_SETUP.md](MANUAL_CONSOLE_SETUP.md) ทำมือทีละคลิกใน Console · [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) เช็กลิสต์ซ้อมเดโม 10 นาที

---

## ประโยชน์ของแอปพลิเคชันและโมเดลธุรกิจ (Application Benefit & Level 5 Viability)

- **แก้ปัญหาจริงของนักลงทุนรายย่อย:** ลดเวลาอ่านข่าวและดูกราฟหุ้นหลายตัวจากวันละ 1–2 ชั่วโมง เหลือเพียง **30 วินาที** ด้วยบทสรุปคะแนน (0–100), สัญญาณ (Buy / Watch / Sell), จุดเข้าซื้อ-ตัดขาดทุน และปัจจัยเสี่ยงภาษาไทย
- **แยกพอร์ตหลายผู้ใช้งาน (Multi-Workspace):** รองรับการสร้างและสลับพอร์ตแยกตามรหัสพอร์ต (Workspace Code) โดยข้อมูลไม่ปนกัน
- **ปรับคำแนะนำตามสไตล์นักลงทุน (Investor Persona):** เลือกโหมดวิเคราะห์ได้ทั้ง **สายปันผลเน้นปลอดภัย (Conservative Dividend)** และ **สายเก็งกำไรระยะสั้น (Short-Term Momentum)**
- **สรุปภาพรวมรายตัวแบบ Decision Dashboard:** ตารางย่อ (สัญญาณ · คะแนน · เปลี่ยนแปลง · ระดับความเสี่ยง) ช่วยให้ตัดสินใจได้ในหน้าเดียว พร้อมป้ายความเสี่ยงต่ำ/กลาง/สูง และอารมณ์ข่าว (บวก/กลาง/ลบ)
- **ศักยภาพเชิงพาณิชย์ (Unit Economics):** ต้นทุนประมวลผลจริงบน AWS (Lambda + DynamoDB + Bedrock) เฉลี่ยต่ำกว่า **0.10 บาทต่อการวิเคราะห์หุ้น 1 ตัว** สามารถต่อยอดเป็นบริการ SaaS รายเดือน (เช่น 199 บาท/เดือน) โดยมีอัตรากำไรขั้นต้นสูงกว่า 85%

---

## สถาปัตยกรรมระบบบน AWS (5 Core AWS Services)

โปรเจกต์นี้ออกแบบแบบ **Zero External API Keys** (ไม่ต้องสมัครคีย์เว็บนอก) และใช้บริการหลักของ AWS จำนวน **5 บริการ** (ไม่นับรวมบริการจัดการพื้นฐานสีม่วงอย่าง IAM, VPC, CloudWatch, CLI และ Cost & Usage Report):

| ลำดับ | บริการ AWS | หน้าที่หลักในระบบ |
|---|---|---|
| 1 | **AWS Lambda (Function URL)** | รันระบบหลังบ้าน FastAPI เสิร์ฟหน้าเว็บ Dashboard และประมวลผลหุ้นแบบขนาน (Parallel) |
| 2 | **Amazon DynamoDB** | จัดเก็บรายชื่อหุ้นแยกตามพอร์ต (CRUD), ประวัติผลวิเคราะห์ และระบบ Smart Cache (TTL) |
| 3 | **Amazon Bedrock** | ประมวลผลตัวเลขเทคนิคและข่าวสารด้วยโมเดล AI เพื่อสร้างแผนเทรดภาษาไทย |
| 4 | **Amazon EventBridge** | ตั้งเวลาปลุก AWS Lambda มาวิเคราะห์หุ้นทุกพอร์ตอัตโนมัติในวันทำการหลังตลาดปิด |
| 5 | **Amazon SNS** | ส่งอีเมลแจ้งเตือนอัตโนมัติเมื่อพบหุ้นที่มีสัญญาณโดดเด่นหรือมีความเสี่ยงสำคัญ |

*(หมายเหตุ: แผนผังสถาปัตยกรรมในสไลด์นำเสนออ้างอิงไอคอนมาตรฐานจาก aws-icons.com)*

### ความเข้ากันได้กับ AWS Academy Learner Lab

โปรเจกต์นี้รันได้ทั้งบนบัญชี AWS ปกติและบน **AWS Academy Learner Lab** (region `us-east-1` / `us-west-2`) โดยใช้ `template.learner-lab.yaml` แทน `template.yaml` เพราะ Learner Lab **ไม่อนุญาตให้สร้าง IAM role** จึงต้องผูก role ที่มีอยู่แล้วชื่อ `LabRole` แทน

ก่อน deploy ให้รัน `python scripts/preflight.py` เพื่อตรวจว่าบริการที่ต้องใช้ (CloudFormation, Lambda, DynamoDB, SNS, EventBridge, Bedrock) เปิดใช้งานได้จริงในบัญชีของคุณ

**คู่มือแยกตามประเภทบัญชี:**
- ⚡ **กลุ่มอื่นที่ต้องการ clone แล้วติดตั้งใน 3 คำสั่ง: [QUICKSTART.md](QUICKSTART.md)** (CloudShell, ไม่ต้องลงอะไรในเครื่อง)
- 🎓 **AWS Academy Learner Lab (เส้นทางหลักของรายวิชา): [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md)**
- ☁️ บัญชี AWS ปกติ: [SETUP_GUIDE.md](SETUP_GUIDE.md)

---

## คู่มือการติดตั้งและรันระบบ (Step-by-Step Reproduction Guide)

> คู่มือแยกตามผู้ใช้:
> - **กลุ่มอื่นทำตามเร็วๆ → [QUICKSTART.md](QUICKSTART.md)** (clone + CloudShell + สคริปต์เดียวจบ)
> - **AWS Academy Learner Lab (ละเอียด) → [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md)**
> - บัญชี AWS ปกติ → [SETUP_GUIDE.md](SETUP_GUIDE.md)

คู่มือนี้ออกแบบให้กลุ่มผู้ทดสอบสามารถติดตั้งระบบทั้งหมดขึ้นบัญชี AWS ของตนเองจนใช้งานได้จริงภายใน **15 นาที** โดยไม่ต้องสมัคร API Key ภายนอกใดๆ

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
4. ถ้าใช้ **Learner Lab** แล้ว Bedrock ถูกบล็อก: แอปยังใช้งานได้ครบ แต่ผลวิเคราะห์จะมาจาก rule-based fallback (ป้ายบนการ์ดจะระบุ) — ควรแจ้งอาจารย์หรือผู้ดูแลแล็บ

### ขั้นตอนที่ 2: ติดตั้งระบบทั้งหมดด้วยคำสั่งเดียว (AWS SAM Deploy)
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
> sam build --use-container -t template.learner-lab.yaml
> sam deploy --guided -t template.learner-lab.yaml
> ```

ในขั้นตอน `sam deploy --guided` ให้กรอกค่าดังนี้:
- **Stack Name:** `ai-equity-copilot`
- **AWS Region:** `us-east-1` (หรือ Region เดียวกับที่เช็ก Bedrock ในขั้นตอนที่ 1)
- **Parameter AlertEmail:** กรอกอีเมลจริงของคุณเพื่อใช้ทดสอบรับจ้งเตือนจาก Amazon SNS
- **Parameter BedrockModelId:** กด Enter เพื่อใช้ค่าเริ่มต้น (หรือระบุ Model ID ที่เปิดไว้)
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
   - เลือกโหมดนักลงทุน แล้วกดปุ่ม **วิเคราะห์พอร์ตด้วย AI** เพื่อดูผลลัพธ์สด
   - กดปุ่ม **ส่งรายงานเข้าอีเมล (SNS)** เพื่อตรวจสอบว่าได้รับอีเมลสรุปผลเข้ากล่องจดหมายจริง

### วิธีลบทรัพยากรทั้งหมดหลังทดสอบเสร็จ (Cleanup)
เพื่อป้องกันค่าใช้จ่ายตกค้างหลังจบการประเมิน สามารถลบทุกบริการทิ้งได้ด้วยคำสั่งเดียว:

```bash
sam delete --stack-name ai-equity-copilot
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
| ใช้ AWS Services อย่างน้อย 4 บริการ (ไม่นับ Purple Service) | **Lambda, DynamoDB, Bedrock, EventBridge, SNS = 5 บริการ** (IAM/CloudWatch ไม่นับตามเกณฑ์) | ✅ |
| Level 3: Complete Application (Web + Database) | CRUD Watchlist, Dashboard, DynamoDB single-table, multi-workspace | ✅ เกินLevel 3 |
| **Level 4:** Automated, Integrated System — 4+ บริการ + external data API + automated value | EventBridge cron ปลุก Lambda วิเคราะห์ทุกพอร์ตวันทำการ → ส่งอีเมล SNS อัตโนมัติ; ข้อมูลภายนอกจาก `yfinance` + Google News RSS; Bedrock สร้างแผนเทรดภาษาไทย | ✅ |
| Deliverable: วิดีโอ/vlog ขั้นตอน implementation | — | ⬜ ต้องอัดเอง |
| Deliverable: Documentation ที่กลุ่มอื่นทำตามได้ทันเวลา | [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md) (Learner Lab) และ [SETUP_GUIDE.md](SETUP_GUIDE.md) (AWS ปกติ) + `scripts/preflight.py` ตรวจความพร้อม 2 นาที | ✅ |
| Demo day: ของจริง + Benefit + Architecture + Demonstration | หน้าเว็บทำงานจริง, ตารางสถาปัตยกรรม 5 บริการ, ตัวเลขต้นทุน token จริง | ✅ (ต้องทำสไลด์/แผนผังเอง) |
| **Level 5:** Commercially Viable — มีคนยอมจ่ายเงินใช้ | Unit economics คำนวณจาก token จริง, ต้นทุน < 0.10 บาท/หุ้น/ครั้ง, แพ็กเกจ 199 บาท/เดือน, จุดคุ้มทุนในหน้าเว็บ | ⚠️ โครงสร้างธุรกิจครบ แต่ยังขาดหลักฐานความต้องการจากตลาด |

### สิ่งที่ต้องทำเพิ่มเพื่อให้ถึง Level 5

1. **หลักฐานความต้องการ:** สำรวจ/สัมภาษณ์นักลงทุนรายย่อย 10–20 คน (แบบฟอร์ม + สรุปผล) ว่าเคยใช้เวลาวิเคราะห์หุ้นนานแค่ไหน และยอมจ่ายเท่าไร
2. **ราคาและต้นทุน:** ใช้ตัวเลขจาก **Business & Cost Calculator** ในหน้าเว็บ (ต้นทุน token จริง) ประกอบการตั้งราคา และแสดง Gross Margin ในสไลด์
3. **แผนธุรกิจสั้นๆ:** กลุ่มลูกค้าเป้าหมาย (นักลงทุนรายย่อย/อาจารย์สอนการเงิน), ช่องทางขาย, และแผนขยาย (แจ้งเตือน Line/Telegram, พอร์ตหลายตลาด)

### ข้อจำกัดที่ต้องรู้ก่อนเดโม

- บน **AWS Academy Learner Lab** สิทธิ์ Bedrock ขึ้นกับแล็บ: ถ้าเรียกไม่ผ่าน แอปยังทำงานครบ 5 บริการ แต่ผลวิเคราะห์จะมาจาก **rule-based fallback** (ป้ายบนการ์ดระบุชัดเจน) — ควรแจ้งอาจารย์ล่วงหน้า
- ข้อมูลราคา/ข่าวมาจาก `yfinance` และ Google News แบบไม่เป็นทางการ: อาจดีเลย์หรือถูกจำกัดอัตราการเรียกได้ในบางช่วง ถ้าดึงข้อมูลไม่ได้ ระบบจะแจ้งเป็นภาษาไทยรายหุ้น ไม่ทำให้ทั้งพอร์ตล่ม

---

## การอ้างอิงแหล่งที่มา (Open-Source Attribution)
โปรเจกต์นี้ได้รับแรงบันดาลใจด้านโครงสร้างรายงาน AI Decision Dashboard และการคำนวณตัวชี้วัดทางเทคนิคจากโปรเจกต์ Open-source [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) (ภายใต้สัญญาอนุญาต **MIT License**) โดยทีมผู้พัฒนาได้ออกแบบสถาปัตยกรรมใหม่ทั้งหมดสำหรับรันแบบ Serverless บน AWS ทั้ง 5 บริการ

**สิ่งที่นำแนวคิดมาปรับใช้ (ไม่ใช่การคัดลอกโค้ด):** รูปแบบสรุปภาพรวมรายตัวแบบ decision dashboard (สัญญาณ/คะแนน/เปลี่ยนแปลง), แนวคิด `news_tone` และ `risk_level` ที่ทำให้ผู้ใช้เห็นความเสี่ยงก่อนตัดสินใจ และแนวคิดการลดจำนวน request ต่อหุ้น (ใช้ `history_metadata` แทน `ticker.info`, ยิงข่าวขนานกับการดึงราคา) ซึ่งลดเวลาต่อหุ้นจาก ~479 ms เหลือ ~269 ms ในการวัดบนเครื่องพัฒนา

**สิ่งที่ต่างจากต้นทางโดยตั้งใจ:** โปรเจกต์นี้ไม่ใช้ API key ภายนอก ไม่พึ่งพาไลบรารีหนักเพิ่มเติม และไม่เพิ่ม AWS service เกิน 5 บริการตามข้อกำหนดของรายวิชา เพิ่มระบบแยกพอร์ตผู้ใช้งาน รองรับตลาดหุ้นไทย (.BK) ปรับโมเดลวิเคราะห์ตามสไตล์นักลงทุน และเชื่อมต่อ Amazon Bedrock โดยตรง
