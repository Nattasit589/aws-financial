# AGENT.md — Master Engineering Specification

คุณคือ Senior Cloud Solutions Architect และ Full-Stack Python Developer หน้าที่ของคุณคือสร้างโปรเจกต์ **AI Equity Co-Pilot (Ultra-Lean AWS Serverless Edition)** ให้สมบูรณ์พร้อมใช้งานและ Deploy ผ่าน AWS SAM ได้จริงตั้งแต่ครั้งแรก

โปรดอ่านกฎเหล็ก สถาปัตยกรรม และข้อกำหนดทุกข้อด้านล่างอย่างเคร่งครัดก่อนเขียนโค้ด

---

## 1. กฎเหล็กด้านสถาปัตยกรรม (Strict Architectural Constraints)

1. **ใช้ AWS Services หลักเพียง 5 บริการเท่านั้น (ห้ามเพิ่มบริการอื่นโดยไม่จำเป็น):**
   - `AWS Lambda` (เปิดใช้ **Lambda Function URL** เพื่อเสิร์ฟทั้งหน้าเว็บ HTML และ REST API ในตัวเดียวกัน)
   - `Amazon DynamoDB` (เก็บข้อมูล Watchlist แยกตาม Workspace, ประวัติผลวิเคราะห์ และระบบ TTL Cache)
   - `Amazon Bedrock` (เรียกใช้งาน LLM ผ่าน `boto3` Bedrock Runtime API `converse` เพื่อความยืดหยุ่นของโมเดล)
   - `Amazon EventBridge` (ตั้งกฎ `Schedule` ปลุก Lambda อัตโนมัติหลังตลาดปิดวันจันทร์–ศุกร์)
   - `Amazon SNS` (สร้าง SNS Topic + Email Subscription เพื่อส่งอีเมลแจ้งเตือนรายงานสรุป)
2. **ห้ามใช้ S3 โฮสต์เว็บ และห้ามใช้ API Gateway:**
   - เพื่อตัดปัญหา CORS, ปัญหา S3 Public Access Block 403 และเพดาน Timeout 29 วินาทีของ API Gateway ให้รัน FastAPI ผ่าน `Mangum` บน **AWS Lambda Function URL** (ตั้ง Timeout ของ Lambda ไว้ที่ `120` วินาที และ Memory `512` MB)
3. **Zero External API Keys (ห้ามบังคับใช้คีย์ภายนอกเด็ดขาด):**
   - ดึงราคาหุ้นย้อนหลังและข้อมูลพื้นฐานผ่าน `yfinance` (ต้องรองรับทั้งหุ้นไทย เช่น `PTT.BK`, `DELTA.BK`, `SCB.BK` และหุ้นสหรัฐฯ เช่น `NVDA`, `AAPL`, `TSLA`)
   - ดึงข่าวสารล่าสุดจาก `yfinance` ควบคู่กับ **Google News RSS** (`https://news.google.com/rss/search?q={query}&hl=th&gl=TH&ceid=TH:th` สำหรับหุ้น `.BK` และ `hl=en-US` สำหรับหุ้นสหรัฐฯ) โดยแปลง XML ด้วยไลบรารีมาตรฐาน `xml.etree.ElementTree` ของ Python
4. **ไลบรารีต้องเบาและ Build บน AWS Lambda ง่าย:**
   - หลีกเลี่ยงไลบรารีที่ติดปัญหา C-extension ตอน Deploy หากไม่จำเป็น ให้คำนวณอินดิเคเตอร์ทางเทคนิคพื้นฐาน (SMA20, SMA50, RSI14, Volume Ratio, Bias Ratio, 52-Week High/Low Distance) จากข้อมูลที่ดึงมาจาก `yfinance` อย่างคลีนและแม่นยำ

---

## 2. โครงสร้างไฟล์โปรเจกต์เป้าหมาย (Target Directory Layout)

รักษาโครงสร้างไฟล์ให้กระชับ คลีน และดูแลรักษาง่ายที่สุดดังนี้:

```text
.
├── README.md                  # คู่มือติดตั้งและรายละเอียดโปรเจกต์
├── AGENT.md                   # เอกสารข้อกำหนดสำหรับ AI Agent
├── QUICKSTART.md              # คู่มือย่อสำหรับกลุ่มอื่น (clone + CloudShell + 3 คำสั่ง)
├── SETUP_LEARNER_LAB.md       # คู่มือติดตั้งสำหรับ AWS Academy Learner Lab (เส้นทางหลัก)
├── SETUP_GUIDE.md             # คู่มือติดตั้งสำหรับบัญชี AWS ปกติ
├── MANUAL_CONSOLE_SETUP.md    # คู่มือสร้างบริการเองทีละคลิกใน Console (ไม่ใช้ SAM)
├── template.yaml              # แม่แบบ AWS SAM สร้างครบทั้ง 5 บริการในคำสั่งเดียว
├── template.learner-lab.yaml  # แม่แบบสำหรับ AWS Academy Learner Lab (ใช้ LabRole ที่มีอยู่)
├── requirements.txt           # ชี้ไปที่ src/requirements.txt (ไฟล์จริงที่ SAM ใช้)
├── scripts/
│   ├── preflight.py           # ตรวจสิทธิ์/บริการก่อน deploy (read-only + ทดสอบ Bedrock 1 ครั้ง)
│   └── deploy_learnerlab.sh   # ติดตั้งจบในคำสั่งเดียว (CloudShell / เครื่องตัวเอง)
└── src/
    ├── requirements.txt       # ไลบรารี Python ที่ SAM ติดตั้งเข้า Lambda
    ├── app.py                 # Entrypoint หลัก (รองรับทั้ง EventBridge Event และ FastAPI/Mangum HTTP)
    ├── market_data.py         # ดึงราคาหุ้น yfinance + คำนวณ Technical Indicators + ดึงข่าว Google News RSS
    ├── analyzer.py            # สร้าง Prompt ตาม Investor Persona + เรียก Amazon Bedrock + คำนวณต้นทุน Token
    ├── db_and_notify.py       # จัดการ CRUD และ Smart Cache บน DynamoDB + ส่งอีเมลผ่าน Amazon SNS
    └── templates/
        └── index.html         # Single-File Web Dashboard (HTML + Tailwind CSS CDN + Vanilla JS)
```

### 2.1 ข้อจำกัดของ AWS Academy Learner Lab (บังคับ)

ผู้ใช้ส่วนใหญ่ของรายวิชานี้รันบน Learner Lab ซึ่งมีข้อจำกัดที่ต้องออกแบบรองรับ:

1. **สร้าง IAM role/policy/user ไม่ได้** → ต้องใช้ role ที่มีอยู่ชื่อ `LabRole` และต้องมี `template.learner-lab.yaml` ที่ระบุ `Role: arn:aws:iam::<AccountId>:role/LabRole` โดยไม่มีบล็อก `Policies` (เพราะ SAM จะสร้าง role ใหม่)
2. **ใช้ได้เฉพาะ region `us-east-1` และ `us-west-2`** → ค่าเริ่มต้นของโปรเจกต์ต้องเป็น `us-east-1`
3. **Credential หมดอายุทุก session (4 ชั่วโมง)** → คู่มือต้องอธิบายการคัดลอก credential ใหม่จาก AWS Details และอาการ `ExpiredToken`
4. **สิทธิ์ Bedrock ขึ้นกับแล็บ** → ต้องตรวจด้วย `scripts/preflight.py` และแอปต้องถอยไปใช้ `rule_fallback` ได้โดยไม่ล่ม (ห้าม 500)
5. **CloudFormation/SAM ใช้ได้** → การ deploy ยังใช้ `sam deploy` ได้ แต่ต้องตอบ `N` ที่คำถาม Allow SAM CLI IAM role creation
6. SAM ยังต้องใช้ **S3 bucket** เก็บ artifact (เป็น bucket ของ SAM เอง ไม่ใช่ static hosting ของหน้าเว็บ จึงไม่ขัดกฎข้อ 2)

---

## 3. รายละเอียดเชิงลึกของแต่ละส่วนประกอบ

### 3.1 แม่แบบโครงสร้างพื้นฐาน (`template.yaml`)
- **Parameters:**
  - `AlertEmail` (Type: String) สำหรับผูก Email Subscription เข้ากับ SNS Topic อัตโนมัติ
  - `BedrockModelId` (Type: String, Default: `amazon.nova-lite-v1:0`) เพื่อให้สลับเป็น `anthropic.claude-3-haiku-20240307-v1:0` หรือโมเดลอื่นได้โดยไม่ต้องแก้โค้ด
  - `CacheTtlSeconds` (Type: Number, Default: `3600`)
- **Resources:**
  - `PortfolioTable` (`AWS::DynamoDB::Table`): BillingMode `PAY_PER_REQUEST`, Partition Key `pk` (String), Sort Key `sk` (String), เปิดใช้งาน `TimeToLiveSpecification` บนฟิลด์ `ttl`
  - `AlertTopic` (`AWS::SNS::Topic`) พร้อม `AlertEmailSubscription` (`AWS::SNS::Subscription` แบบ `email`)
  - `StockCopilotFunction` (`AWS::Serverless::Function`):
    - `Runtime: python3.12`, `Handler: app.handler`, `CodeUri: src/`, `Timeout: 120`, `MemorySize: 512`
    - `FunctionUrlConfig`: `AuthType: NONE` พร้อมเปิด `Cors` (`AllowOrigins: ["*"]`, `AllowMethods: ["*"]`, `AllowHeaders: ["*"]`)
    - `Events`: ผูก `DailyMarketCloseSchedule` (`Type: Schedule`, `Schedule: cron(15 10 ? * MON-FRI *)` ซึ่งตรงกับ 17:15 น. เวลาไทยหลังตลาดหุ้นไทยปิด)
    - `Policies`: ให้สิทธิ์ `DynamoDBCrudPolicy` บนตาราง, `SNSPublishMessagePolicy` บน Topic และ IAM Statement อนุญาต `bedrock:InvokeModel`
- **Outputs:** แสดงค่า `DashboardUrl` (ค่าจาก `StockCopilotFunctionUrl.FunctionUrl`), `DynamoDBTableName` และ `SNSTopicArn`
- **เวอร์ชัน Learner Lab (`template.learner-lab.yaml`):** ไฟล์นี้ต้องมีเพิ่ม 2 Parameters — `AlertEmail` (เว้นว่างได้, มี `Condition: HasAlertEmail`) และ `LabRoleArn` (เว้นว่าง = ใช้ `arn:aws:iam::<AccountId>:role/LabRole`, มี `Condition: HasCustomRole`), ใช้ `Role:` แทน `Policies:` และมี Output เพิ่ม `ExecutionRole`

### 3.2 ระบบฐานข้อมูล DynamoDB (`src/db_and_notify.py`)
ใช้ Single-Table Design เพื่อเก็บทั้งรายชื่อหุ้นในพอร์ตและ Cache ผลการวิเคราะห์:
- **ข้อมูล Watchlist ของแต่ละพอร์ต:**
  - `pk`: `WORKSPACE#{workspace_id}` (เช่น `WORKSPACE#AJARN-DEMO`)
  - `sk`: `WATCHLIST`
  - ฟิลด์ข้อมูล: `symbols` (List ของชื่อหุ้น เช่น `["PTT.BK", "ADVANC.BK", "NVDA"]`), `persona` (`dividend` หรือ `momentum`), `updated_at`
- **ข้อมูลผลวิเคราะห์และ Smart Cache:**
  - `pk`: `WORKSPACE#{workspace_id}`
  - `sk`: `ANALYSIS#{symbol}#{persona}`
  - ฟิลด์ข้อมูล: `analysis_data` (JSON ผลวิเคราะห์จาก AI + ราคา + อินดิเคเตอร์ + ต้นทุน Token), `analyzed_at`, `ttl` (Epoch timestamp ปัจจุบัน + `CacheTtlSeconds`)
- **ประวัติสำหรับรันอัตโนมัติ (EventBridge):** มีฟังก์ชันดึงรายการ `WORKSPACE#*` ล่าสุดเพื่อนำไปรันอัปเดตอัตโนมัติตามรอบเวลา

### 3.3 ระบบดึงข้อมูลและวิเคราะห์ด้วย AI (`src/market_data.py` & `src/analyzer.py`)
1. **การดึงข้อมูลและคำนวณเทคนิค (`market_data.py`):**
   - ปรับชื่อหุ้นเป็นตัวพิมพ์ใหญ่และตัดช่องว่างอัตโนมัติ
   - ดึงราคาย้อนหลัง **1 ปี** จาก `yfinance` (จำเป็นสำหรับ 52-Week High/Low) แล้วคำนวณราคาล่าสุด, เปอร์เซ็นต์เปลี่ยนแปลงรายวัน, SMA20, SMA50, RSI (14 วัน), Bias Ratio เทียบ SMA20, สัดส่วน Volume วันนี้เทียบค่าเฉลี่ย 10 วัน, ระยะห่าง 52-Week High/Low และความผันผวนจริง 20 วัน (`volatility_20d_pct`)
   - ดึงหัวข้อข่าวล่าสุดไม่เกิน 5 ข่าว (รวมจาก `yfinance` และ Google News RSS)
   - **ประสิทธิภาพ (บังคับ):** ใช้ `history_metadata` จาก response เดียวกันเพื่อเอาชื่อบริษัท/สกุลเงิน/ตลาด ห้ามเรียก `ticker.info` (ช้าและถูกจำกัดอัตรา) และยิง Google News RSS ขนานกับการดึงราคาเพื่อลด latency ต่อหุ้น
2. **การเรียกใช้ Amazon Bedrock (`analyzer.py`):**
   - ใช้ `boto3.client("bedrock-runtime").converse(...)` เพื่อรองรับทั้งตระกูล Amazon Nova และ Anthropic Claude โดยใช้โค้ดชุดเดียวกัน
   - รองรับ 2 โหมดนักลงทุน (`persona`):
     - `dividend`: เน้นความมั่นคง พื้นฐานธุรกิจ แนวรับปลอดภัย และการถือครองระยะกลาง-ยาว
     - `momentum`: เน้นจังหวะเทคนิค กระแสข่าวเร่งราคา จุดเข้าทำกำไร และจุดตัดขาดทุน (Stop Loss) ที่ชัดเจน
   - บังคับให้ AI ตอบกลับเป็นโครงสร้าง **JSON ที่ถูกต้อง** ประกอบด้วย:
     - `score` (ตัวเลข 0–100)
     - `signal` (`BUY`, `WATCH`, หรือ `SELL`)
     - `news_tone` (`บวก`, `กลาง`, หรือ `ลบ`) — อารมณ์ข่าวล่าสุด
     - `trend_summary` (สรุปแนวโน้มภาษาไทยสั้นกระชับ) + `risk_level` (`LOW`/`MEDIUM`/`HIGH` คำนวณจากตัวเลขจริงโดยไม่ใช้ token) และ `risk_reasons`
     - `action_plan` (`entry_zone`, `stop_loss`, `take_profit`, `checklist` 3 ข้อภาษาไทย)
     - `catalysts` (รายการปัจจัยบวกภาษาไทย 2–3 ข้อ)
     - `risks` (รายการความเสี่ยงที่ต้องระวังภาษาไทย 2–3 ข้อ)
   - **การคำนวณต้นทุนจริง (Unit Economics Proof):** อ่านค่า `usage.inputTokens` และ `usage.outputTokens` จากผลตอบกลับของ `converse` แล้วคำนวณต้นทุนจริงเป็นดอลลาร์และเงินบาทแนบกลับไปกับผลลัพธ์ทุกครั้ง พร้อมมีระบบ Fallback สรุปผลจากกฎทางเทคนิคหากกรณีบัญชีผู้ทดสอบยังไม่ได้เปิดสิทธิ์ Bedrock เพื่อไม่ให้แอปล่ม
3. **การประมวลผลแบบขนาน (Parallel Execution):**
   - ใช้ `concurrent.futures.ThreadPoolExecutor(max_workers=5)` วิเคราะห์หุ้นทุกตัวในพอร์ตพร้อมกัน และสร้างบทสรุปภาพรวมความเสี่ยงของทั้งพอร์ต (`portfolio_summary`) ให้ด้วย

### 3.4 ตัวจัดการหลักแบบควบสองหน้าที่ (`src/app.py`)
ฟังก์ชัน `handler(event, context)` ต้องแยกแยะประเภทคำสั่งได้แม่นยำ:
- **กรณีที่ 1 (EventBridge Scheduled Trigger):** หากตรวจพบ `event.get("source") == "aws.events"` หรือ `"detail-type" in event` ให้ดึงพอร์ตที่มีอยู่ใน DynamoDB มาวิเคราะห์อัปเดตอัตโนมัติ และส่งอีเมลสรุปสัญญาณเด่นเข้า Amazon SNS
- **กรณีที่ 2 (HTTP Function URL Request):** ส่งต่อให้ `Mangum(fastapi_app)(event, context)` จัดการเส้นทางต่อไปนี้:
  - `GET /`: ส่งหน้าเว็บ `templates/index.html` ออกไปแสดงผล
  - `GET /api/workspace/{workspace_id}`: ดึงข้อมูลรายชื่อหุ้น โหมดนักลงทุน และผลวิเคราะห์ล่าสุดจาก DynamoDB
  - `POST /api/workspace/{workspace_id}/stocks`: เพิ่มหุ้นเข้า Watchlist (จำกัดไม่เกิน 10 ตัวต่อพอร์ตเพื่อความเร็ว)
  - `DELETE /api/workspace/{workspace_id}/stocks/{symbol}`: ลบหุ้นออกจาก Watchlist
  - `POST /api/workspace/{workspace_id}/persona`: บันทึกโหมดนักลงทุน (`dividend` / `momentum`) ลง DynamoDB
  - `POST /api/workspace/{workspace_id}/analyze`: สั่งวิเคราะห์หุ้นทั้งพอร์ตแบบขนาน (รองรับพารามิเตอร์ `force_refresh=true` เพื่อข้าม Cache)
  - `POST /api/workspace/{workspace_id}/notify`: สั่งส่งรายงานสรุปของพอร์ตปัจจุบันเข้า Amazon SNS ทันที (สำหรับกดโชว์อาจารย์สดๆ บนเวที Demo และให้เพื่อนกลุ่มอื่นกดทดสอบอีเมล)

### 3.5 หน้าเว็บ Single-File Dashboard (`src/templates/index.html`)
ออกแบบ UI ให้สวยงาม ทันสมัย ระดับโปรดักชัน SaaS (โทนสี Dark/Slate การเงินมืออาชีพ ใช้ Tailwind CSS CDN) มีองค์ประกอบครบถ้วนดังนี้:
- **แถบจัดการพอร์ตด้านบน (Workspace Bar):** ช่องกรอก `Workspace Code` (ค่าเริ่มต้นเช่น `DEMO-PORT`) พร้อมปุ่มสลับพอร์ตได้ทันที และปุ่มเลือกโหมดนักลงทุน (`สายปันผลปลอดภัย` / `สายเก็งกำไรระยะสั้น`)
- **ส่วนจัดการ Watchlist (CRUD):** ช่องพิมพ์เพิ่มรหัสหุ้นพร้อมปุ่มตัวอย่างลัด (`PTT.BK`, `ADVANC.BK`, `NVDA`, `AAPL`), รายการหุ้นที่กดลบได้, ปุ่ม **วิเคราะห์พอร์ตด้วย AI** (พร้อมตัวเลือกบังคับดึงข้อมูลสดไม่ใช้ Cache) และปุ่ม **ส่งรายงานเข้าอีเมล (SNS)**
- **การ์ดสรุปสุขภาพพอร์ตรวม (Portfolio Health Banner):** แสดงคะแนนเฉลี่ยของพอร์ต สัดส่วนสัญญาณ Buy/Watch/Sell, สัดส่วนความเสี่ยง (ต่ำ/กลาง/สูง) และคำแนะนำภาพรวม
- **ตารางสรุปภาพรวมรายตัว (Decision Summary Rows):** บรรทัดย่อต่อหุ้น แสดงรหัส, สัญญาณ, เปลี่ยนแปลงวันนี้, คะแนน และป้ายความเสี่ยง — อ่านจบพอร์ตได้ในหน้าเดียว
- **การ์ด AI Decision Dashboard รายตัว:** แสดงราคา เปอร์เซ็นต์เปลี่ยนแปลง ค่า RSI/SMA (+ความผันผวน 20 วัน) เกจคะแนนเต็ม 100 ป้ายสัญญาณสีชัดเจน ป้ายระดับความเสี่ยงพร้อมเหตุผล ป้าย `news_tone` (ข่าวบวก/กลาง/ลบ) กรอบแผนปฏิบัติการ (จุดรับ/ต้าน/ตัดขาดทุน) และรายการปัจจัยเร่งเทียบความเสี่ยง พร้อมป้ายบอกสถานะว่าดึงจาก `Smart Cache` หรือ `Live Bedrock AI`
- **ประสิทธิภาพของหน้าเว็บ:** ใช้ `preconnect` กับ CDN, แสดง skeleton ระหว่างรอผล และบันทึกผลลัพธ์ล่าสุดลง `localStorage` เพื่อให้เปิดหน้าซ้ำเห็นผลได้ทันที (แล้วค่อยอัปเดตจาก API)
- **แท็บ/ป๊อปอัป Business & Cost Calculator (สำหรับโชว์คะแนน Level 5):** แสดงต้นทุน Token จริงของการกดวิเคราะห์รอบล่าสุด (หน่วยสตางค์) พร้อมเครื่องคิดเลขจำลองรายได้เทียบต้นทุน AWS หากเปิดขายแพ็กเกจรายเดือน (เช่น 199 บาท/เดือน)

---

## 4. ลำดับขั้นตอนการลงมือทำสำหรับ Agent (Execution Checklist)

1. สร้างไฟล์ `src/requirements.txt` (ระบุเฉพาะไลบรารีที่จำเป็น: `fastapi`, `mangum`, `yfinance`, `boto3`) และ `requirements.txt` ที่ root ชี้มาที่ไฟล์นั้นด้วย `-r src/requirements.txt`
2. สร้างไฟล์ `template.yaml` ตรวจสอบไวยากรณ์ AWS SAM ให้ถูกต้องครบทั้ง 5 บริการและ IAM Policies
3. พัฒนาโมดูล `src/market_data.py`, `src/db_and_notify.py`, `src/analyzer.py` และ `src/app.py` พร้อมจัดการ Error Handling ทุกจุด (เช่น พิมพ์ชื่อหุ้นผิด ตลาดปิด หรือติดข้อจำกัดเครือข่าย ต้องคืนข้อความแจ้งเตือนภาษาไทยที่เข้าใจง่าย ไม่ปล่อยให้เกิด 500 Internal Server Error)
4. พัฒนาหน้าเว็บ `src/templates/index.html` เชื่อมต่อกับ API ทุกเส้นทางด้วย Relative Path (`/api/...`) เพื่อให้ทำงานผ่าน Lambda Function URL ได้ทันทีโดยไม่ต้องแก้ URL
5. ทดสอบรันโลคอลเบื้องต้นและตรวจสอบว่าคำสั่ง `sam validate` หรือ `sam build` สามารถทำงานผ่านได้โดยไม่มีข้อผิดพลาด
