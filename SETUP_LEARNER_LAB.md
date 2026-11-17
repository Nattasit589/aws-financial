# SETUP — AWS Academy Learner Lab (คู่มือหลัก)

> อยากได้ฉบับย่อสำหรับกลุ่มอื่น (clone + CloudShell + คำสั่งเดียว)? ดู **[QUICKSTART.md](QUICKSTART.md)**


คู่มือนี้เขียนสำหรับการรันโปรเจกต์ **AI Equity Co-Pilot** บน **AWS Academy Learner Lab** ที่ Region `us-east-1`
ทำตามลำดับแล้วจบได้ใน **20–30 นาที** (ครั้งแรก) — ถ้าเคยทำแล้ว ครั้งต่อไปเหลือแค่ 3 คำสั่ง

> ถ้าใช้บัญชี AWS ส่วนตัว/บริษัท (ไม่ใช่ Learner Lab) ให้ใช้ **[SETUP_GUIDE.md](SETUP_GUIDE.md)** แทน

---

## 0. สิ่งที่จะถูกสร้าง และค่าใช้จ่าย

| บริการ | สิ่งที่เกิดขึ้น |
|---|---|
| AWS Lambda + Function URL | ฟังก์ชัน `ai-equity-copilot-app` เสิร์ฟหน้าเว็บ + REST API ที่ URL เดียว |
| Amazon DynamoDB | ตาราง `ai-equity-copilot-PortfolioTable-xxxx` เก็บ Watchlist + Smart Cache (TTL 1 ชม.) |
| Amazon Bedrock | เรียกโมเดล `amazon.nova-lite-v1:0` สร้างแผนเทรดภาษาไทย |
| Amazon EventBridge | กฎ `daily-market-close-analysis` ปลุก Lambda จ-ศ 17:15 น. เวลาไทย |
| Amazon SNS | Topic + Email Subscription ส่งรายงานสรุป |

**ค่าใช้จ่าย:** Learner Lab ให้เครดิต $50–$100 ต่อคน (แล้วแต่การตั้งค่าของอาจารย์) โปรเจกต์นี้ใช้จริงน้อยมาก
Bedrock Nova Lite คิดประมาณ **0.002–0.01 บาทต่อหุ้น 1 ครั้ง** — วิเคราะห์ 10 หุ้น x 10 รอบ ยังไม่ถึง 1 บาท
Lambda/DynamoDB/EventBridge/SNS อยู่ใน Free Tier

> ⚠️ ถ้าใช้เครดิตหมด แล็บจะถูกปิดและทรัพยากรหายทั้งหมด — ลบ stack เมื่อเลิกใช้ (หัวข้อ 11)

---

## 1. สิ่งที่ต้องติดตั้งในเครื่อง

| โปรแกรม | จำเป็น | หมายเหตุ |
|---|---|---|
| **AWS CLI v2** | ✅ | ใช้คัดลอก credential ของแล็บมาสั่งงาน |
| **AWS SAM CLI** | ✅ | deploy ทั้ง stack ด้วยคำสั่งเดียว |
| **Python 3.12** | ✅ | ให้ SAM build ตรงกับ Lambda runtime |
| **Docker Desktop** | ✅ (แนะนำ) | ใช้กับ `sam build --use-container` — ต้องเปิดค้างไว้ |
| **Git** | ไม่บังคับ | ถ้าโคลนโค้ดจาก repo |

ตรวจสอบ:

```bash
aws --version
sam --version
python --version
docker --version
```

**Windows:** ให้รันทุกคำสั่งใน **Git Bash**, **WSL** หรือ **PowerShell** (คู่มือนี้ใช้ syntax bash)
**หมายเหตุ:** terminal ที่อยู่ในหน้า Learner Lab มี AWS CLI + credential พร้อมใช้ แต่ **ไม่มี SAM CLI** และไม่แนะนำให้ build ที่นั่น — ให้ build บนเครื่องตัวเอง

---

## 2. เริ่ม session และเอา credential

Learner Lab ให้ credential แบบชั่วคราว **หมดอายุทุก 4 ชั่วโมง**

1. เข้า **AWS Academy** → เลือก course → **Learner Lab**
2. กด **Start Lab** แล้วรอจนจุดข้างคำว่า **AWS** เป็น **สีเขียว**
3. ดูแถบ **Budget** ด้านบนไว้ (เช่น `$37 remaining`) — ใช้หมดแล้วแล็บจะหยุดทำงาน
4. คลิก **AWS Details** → ที่บรรทัด **AWS CLI** กด **Show** จะเห็น 3 ค่า:
   - `aws_access_key_id`
   - `aws_secret_access_key`
   - `aws_session_token` ← ตัวนี้สำคัญมาก ห้ามลืม
5. ตั้งค่าในเครื่อง:

```bash
aws configure
# Access Key ID     : <aws_access_key_id>
# Secret Access Key : <aws_secret_access_key>
# Default region    : us-east-1
# Output format     : json

aws configure set aws_session_token "<aws_session_token>"
aws configure set region us-east-1
```

6. ตรวจว่าผ่าน:

```bash
aws sts get-caller-identity
```

ต้องเห็น `Arn` ขึ้นต้นด้วย `arn:aws:sts::...:assumed-role/voclabs/...`
ถ้า error ให้กลับไปข้อ 2 (credential หมดอายุ/คัดลอกไม่ครบ)

> **Learner Lab ใช้ได้เฉพาะ `us-east-1` และ `us-west-2`** และในคู่มือนี้ใช้ `us-east-1` ตามลิงก์คอนโซลของคุณ — ตั้งให้ตรงกันตลอด (CLI, SAM, Bedrock)

---

## 3. ตรวจความพร้อมก่อน deploy (ห้ามข้าม)

```bash
pip install boto3
python3 scripts/preflight.py
```

สคริปต์จะตรวจแบบ read-only ทั้งหมด (ยกเว้นเรียก Bedrock 1 ครั้งด้วย `maxTokens=8` ต้นทุนแทบเป็นศูนย์) แล้วสรุปให้ว่าอะไรผ่าน/ไม่ผ่าน

ผลที่ควรเห็น (บัญชี Learner Lab ปกติ):

```
✅ AWS credential & identity
✅ ตรวจชนิดบัญชี              AWS Academy / Vocareum (Learner Lab)
✅ IAM role 'LabRole' มีอยู่จริง
✅ Role ยอมให้ Lambda สวมสิทธิ์
✅ CloudFormation (SAM deploy)
✅ S3 (bucket เก็บ artifact)
✅ Lambda
✅ DynamoDB
✅ SNS
✅ EventBridge / Events
✅ CloudWatch Logs
✅ Lambda Function URL (สิทธิ์)
✅ Bedrock (เรียกโมเดลจริง)
ผลลัพธ์: ✅ พร้อม deploy (ผ่านทุกบริการหลัก)
```

อ่านผลอย่างไร:

| อาการ | ความหมาย | ทำอะไรต่อ |
|---|---|---|
| ❌ **AWS credential** | ยังไม่ Start Lab / token หมดอายุ | กลับไปข้อ 2 |
| ❌ **IAM role 'LabRole'** | แล็บนี้ใช้ชื่อ role อื่น | deploy ด้วย `--parameter-overrides LabRoleArn=arn:aws:iam::<AccountId>:role/<ชื่อ role>` |
| ❌ **CloudFormation / Lambda / S3** | แล็บบล็อกบริการนั้น | แจ้งอาจารย์/ผู้ดูแลแล็บ (ปกติ Learner Lab เปิดให้) |
| ❌ **Bedrock** | LabRole ไม่มีสิทธิ์ `bedrock:InvokeModel` | ไปหัวข้อ 4.2 — แอปยังใช้งานได้ |
| ❌ **Lambda Function URL** | แล็บบล็อกรุ่นเก่า | แจ้งผู้ดูแลแล็บ (โปรเจกต์นี้ออกแบบเลี่ยง API Gateway ตามสเปก) |

---

## 4. Amazon Bedrock บน Learner Lab

### 4.1 ถ้า preflight ผ่าน
ไม่ต้องทำอะไร ระบบจะใช้ AI จริง (`amazon.nova-lite-v1:0`) และการ์ดผลวิเคราะห์จะขึ้นป้าย **Live Bedrock AI**

### 4.2 ถ้า preflight ไม่ผ่าน
แอป **ยังทำงานครบทุกบริการ** และจะไล่ตามลำดับ **Bedrock → Google Gemini (ถ้าตั้ง key) → rule-based** (ป้ายบนการ์ดจะระบุว่าผลมาจากชั้นไหน + มีคำอธิบายสีเหลืองท้ายการ์ด) ซึ่งยังนับเป็นระบบอัตโนมัติเต็มรูปแบบตามเกณฑ์ Level 4 แต่ควรลองตามลำดับนี้ก่อนยอมแพ้:

**ลำดับที่ 0 — เปิด AI สำรอง Google Gemini (ไม่บังคับ)**

ถ้าแล็บนี้บล็อก Bedrock จริง ๆ และต้องการให้เดโมได้ผลจาก AI จริง: ขอ key ฟรีที่ [Google AI Studio](https://aistudio.google.com/apikey) แล้วรัน

```bash
bash scripts/deploy_learnerlab.sh --gemini-key AIza...
```

หรือรัน `bash scripts/deploy_learnerlab.sh` เฉย ๆ แล้ววาง key เมื่อสคริปต์ถาม — **ไม่มีการเพิ่ม AWS service** (key ส่งเป็น CloudFormation Parameter `NoEcho`) และระบบจะลองซ้ำ/สลับโมเดลสำรองเองเมื่อ Google ตอบ 503

**ลำดับที่ 1 — ลอง cross-region inference profile**

```bash
python3 scripts/preflight.py --model us.amazon.nova-lite-v1:0
```

ถ้าผ่าน ให้ deploy ซ้ำด้วย template ที่ build แล้ว (ต้อง build ตามหัวข้อ 5 ก่อน):

```bash
sam deploy --guided -t .aws-sam/build/template.yaml \
  --parameter-overrides BedrockModelId=us.amazon.nova-lite-v1:0
```

**ลำดับที่ 2 — ขอให้อาจารย์/ผู้ดูแลแล็บเปิดสิทธิ์**
ส่งข้อมูลในหัวข้อ 14 ให้เขาเปิด action `bedrock:InvokeModel` (และ `bedrock:InvokeModelWithResponseStream`) ใน `LabRole`

**ลำดับที่ 3 — เดโมตามจริง**
อธิบายตรงๆ ว่าแล็บจำกัดสิทธิ์ Bedrock จึงมี fallback ระดับProduction ที่คำนวณจาก RSI/SMA/Volume ให้ดู และชี้ว่าถ้าเปิดสิทธิ์จะได้ผลจาก LLM ทันทีโดยไม่ต้องแก้โค้ด (แค่เปลี่ยน parameter) — นี่คือความสามารถด้าน resilience ที่อาจารย์มักให้คะแนน

---

## 5. Build แพ็กเกจ

```bash
sam build --use-container -t template.learner-lab.yaml
```

- ครั้งแรกดาวน์โหลด Docker image `python3.12` + ติดตั้ง `fastapi`, `mangum`, `yfinance` (ดึง pandas/numpy) → ใช้เวลา **3–8 นาที**
- **ต้องเปิด Docker Desktop ค้างไว้** ไม่งั้นได้ `Cannot connect to the Docker daemon`
- ต้องมี `--use-container` เพราะ pandas/numpy เป็น binary ที่ผูกกับ OS — build บน Windows ตรงๆ แล้วขึ้น Lambda (Linux) จะได้ `ImportError: numpy`
- ถ้าเครื่องไม่มี Docker: ใช้ WSL แล้ว build ในนั้น (SAM CLI ต้องติดตั้งใน WSL ด้วย)

สำเร็จแล้วจะเห็น:

```
Build Succeeded
Built Resources:
  Function: StockCopilotFunction
```

---

## 6. Deploy

```bash
sam deploy --guided -t .aws-sam/build/template.yaml --config-env learnerlab
```

> **ทำไมต้องชี้ `.aws-sam/build/template.yaml`:** ไฟล์นี้คือ template ที่ผ่าน `sam build` แล้วจึงชี้ไปที่โค้ด+ไลบรารีที่ติดตั้งไว้ ถ้าใส่ `-t template.learner-lab.yaml` (ไฟล์ต้นฉบับ) SAM จะแพ็กแค่ `src/` โดยไม่มี `fastapi`/`pandas` → Lambda ขึ้น `ImportError` ตอนเรียกครั้งแรก

> `--config-env learnerlab` ทำให้ค่าเหล่านี้ถูกจำแยกจาก template อื่นใน `samconfig.toml` (ครั้งต่อไปสั่ง `sam deploy -t .aws-sam/build/template.yaml --config-env learnerlab` ได้เลย)

ตอบคำถามดังนี้:

| คำถาม | ตอบ | เหตุผล |
|---|---|---|
| Stack Name | `ai-equity-copilot` | ใช้ชื่อนี้ตลอด |
| AWS Region | `us-east-1` | ต้องตรงกับ region ของแล็บ |
| Parameter AlertEmail | อีเมลจริง หรือเว้นว่าง | เว้นว่างได้ถ้ายังไม่ต้องการอีเมล |
| Parameter BedrockModelId | Enter | `amazon.nova-lite-v1:0` |
| Parameter CacheTtlSeconds | Enter | 3600 วินาที |
| Parameter LabRoleArn | Enter | ใช้ `LabRole` อัตโนมัติ |
| Confirm changes before deploy | `N` | ไม่ต้องกดยืนยันซ้ำ |
| **Allow SAM CLI IAM role creation** | **`N`** | **สำคัญที่สุด** — Learner Lab สร้าง IAM role ไม่ได้ |
| Disable rollback | `N` | ให้ rollback อัตโนมัติเมื่อพัง |
| `... has no authentication. Is this okay?` | `y` | ให้เปิดหน้าเว็บผ่าน Function URL ได้ |
| Create managed S3 bucket? (ถ้าถูกถาม) | `Y` | SAM ใช้เก็บ artifact |
| Save arguments to configuration file | `Y` | ครั้งหน้าไม่ต้องตอบใหม่ |

> ถ้าไม่ถูกถามเรื่อง IAM role creation ก็ไม่เป็นไร (template นี้ไม่มี IAM resource ให้สร้าง)

สำเร็จจะเห็น `Successfully created/updated stack - ai-equity-copilot in us-east-1`
แล้วดึงลิงก์หน้าเว็บ:

```bash
aws cloudformation describe-stacks \
  --stack-name ai-equity-copilot \
  --query "Stacks[0].Outputs" \
  --output table
```

จะได้ `DashboardUrl` (รูปแบบ `https://xxxxxxxxxxxx.lambda-url.us-east-1.on.aws/`), `DynamoDBTableName`, `SNSTopicArn` และ `ExecutionRole` (ใช้ตรวจสอบว่า Lambda ผูกกับ `LabRole` ถูกตัว)

---

## 7. ยืนยันอีเมล SNS

ถ้ากรอก `AlertEmail` ตอน deploy:

1. เปิดกล่องจดหมาย → หาหัวข้อ **`AWS Notification - Subscription Confirmation`** (เช็ค Spam ด้วย)
2. กด **Confirm subscription** (ลิงก์มีอายุจำกัด ถ้าเลยกำหนดให้สร้าง subscription ใหม่)

ถ้าเว้นว่างไว้ตอน deploy แต่ภายหลังอยากได้อีเมล:

1. เปิด **AWS Console** → **Amazon SNS** → **Topics** → เลือก `ai-equity-copilot-AlertTopic-xxxx`
2. **Create subscription** → Protocol: `Email` → Endpoint: อีเมลของคุณ → **Create subscription**
3. ไปกดยืนยันในอีเมล

ตรวจสถานะ:

```bash
aws sns list-subscriptions-by-topic --topic-arn "<SNSTopicArn>" \
  --query "Subscriptions[].SubscriptionArn" --output text
```

ถ้าได้ `PendingConfirmation` แปลว่ายังไม่กดยืนยัน (ปุ่ม "ส่งรายงาน" จะยังไม่ถึงอีเมล)

---

## 8. ใช้งานหน้าเว็บ

เปิด `DashboardUrl` (ครั้งแรกช้า 1–3 วินาทีเพราะ cold start)

1. **Workspace Code** → พิมพ์ `DEMO-$(date +%H%M)` หรือชื่อกลุ่ม เช่น `DEMO-CS446` → กด **โหลดพอร์ต**
   (ข้อมูลแยกตามรหัสนี้ ไม่ปนกับเพื่อนในกลุ่ม)
2. **สไตล์นักลงทุน** → *สายปันผลปลอดภัย* หรือ *สายเก็งกำไรสั้น* (เปลี่ยน prompt ที่ส่งให้ AI)
3. **เพิ่มหุ้น** → หุ้นไทยต้องลงท้าย `.BK` (`PTT.BK`, `ADVANC.BK`, `DELTA.BK`) / หุ้นสหรัฐฯ ใช้รหัสตรงๆ (`NVDA`, `AAPL`) — สูงสุด 10 ตัว
4. **บังคับดึงข้อมูลสด** → ติ๊กเมื่ออยากข้าม Smart Cache (ปกติ cache 1 ชม.)
5. **วิเคราะห์พอร์ตด้วย AI** → รอ 15–60 วินาที (ปุ่มนับวินาทีให้เห็น)
6. **ส่งรายงานเข้าอีเมล (SNS)** → ส่งสรุปรอบล่าสุดทันที
7. **Business & Cost** → ต้นทุน token จริง + เครื่องคิดเลขกำไร/จุดคุ้มทุน (ใช้โชว์ Level 5)

หน้าจอจะแสดง **ตารางสรุปภาพรวมรายตัว** (สัญญาณ · เปลี่ยนแปลง · คะแนน · ความเสี่ยง) แล้วตามด้วยการ์ดรายละเอียดของแต่ละหุ้น

อ่านการ์ดผลลัพธ์:

| ป้าย | ความหมาย |
|---|---|
| `Live Bedrock AI` | เรียกโมเดลใหม่จริงในรอบนี้ |
| `Smart Cache` | ผลจาก DynamoDB ภายใน 1 ชม. (ไม่เสีย token) |
| `Rule-based Fallback` | Bedrock ใช้ไม่ได้ ระบบสรุปด้วยกฎเทคนิคให้ก่อน |
| `เสี่ยงต่ำ/ปานกลาง/สูง` | คำนวณจากความผันผวน 20 วัน, RSI สุดโต่ง, Bias และคะแนน ( hover เพื่อดูเหตุผล) |
| `ข่าวบวก/กลาง/ลบ` | อารมณ์ข่าวล่าสุดที่ AI ประเมิน (`news_tone`) |

---

## 9. พิสูจน์ทั้ง 6 บริการตอนเดโม

รันใน terminal ที่มี credential (เครื่องตัวเอง หรือ terminal ในหน้า Learner Lab)

```bash
# 1) Lambda + URL
aws lambda get-function-url-config --function-name ai-equity-copilot-app

# 2) DynamoDB (ต้องเห็น item ของ Workspace ที่เพิ่งใช้)
aws dynamodb scan --table-name "<DynamoDBTableName>" --max-items 5

# 2.5) S3 (ต้องเห็นสำเนารายงาน reports/<พอร์ต>/<วันที่>/...)
aws s3 ls "s3://<ReportBucketName>/reports/" --recursive

# 3) SNS (ต้องมี subscription ที่ confirmed)
aws sns list-subscriptions-by-topic --topic-arn "<SNSTopicArn>"

# 4) EventBridge (ต้องเห็นกฎ + ตารางรอบถัดไป)
aws events describe-rule --name daily-market-close-analysis

# 5) CloudWatch Logs (เห็น log การเรียก Bedrock)
aws logs tail /aws/lambda/ai-equity-copilot-app --follow
```

ลำดับการเดโมที่แนะนำ: **หน้าเว็บ → กดวิเคราะห์ → ชี้การ์ด score/แผนเทรด → เปิด DynamoDB item → กดส่งอีเมล → เปิดกล่องจดหมาย → โชว์ EventBridge rule → โชว์ CloudWatch log**

---

## 10. แก้โค้ดแล้ว deploy ซ้ำ

```bash
sam build --use-container -t template.learner-lab.yaml
sam deploy -t .aws-sam/build/template.yaml --config-env learnerlab
```

**ทุกครั้งที่กลับมาทำงานใหม่ (คนละ session):** credential เก่าหมดอายุแล้ว ให้ทำข้อ 2 ซ้ำ (Start Lab → AWS Details → `aws configure set aws_session_token ...`)
อาการที่เจอถ้าลืม: `ExpiredToken`, `InvalidClientTokenId`, `The security token included in the request is expired`

---

## 11. ลบทรัพยากร / ประหยัดเครดิต

หลังส่งงานหรือเลิกใช้:

```bash
sam delete --stack-name ai-equity-copilot
```

- ลบทั้งหมด **รวมข้อมูล DynamoDB และ SNS subscription** (กู้คืนไม่ได้)
- ถ้าถูกถามให้ยืนยัน S3 bucket และ stack → ตอบ `y`
- Learner Lab จะล้างทรัพยากรเองเมื่อจบ course แต่การลบเองช่วยให้เครดิตไม่ถูกใช้ต่อ

---

## 12. แก้ปัญหาที่พบบ่อย (Learner Lab)

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| `ExpiredToken` / `InvalidClientTokenId` | session 4 ชม. หมด | Start Lab → คัดลอก credential ใหม่ → `aws configure set aws_session_token ...` |
| `not authorized to perform: iam:CreateRole` ตอน deploy | ตอบ `Y` ที่ Allow SAM CLI IAM role creation หรือใช้ `template.yaml` ผิดไฟล์ | ลบ stack ที่พัง (`sam delete`) แล้ว deploy ใหม่ด้วย `-t .aws-sam/build/template.yaml` (หลัง `sam build -t template.learner-lab.yaml`) และตอบ `N` |
| `Cannot connect to the Docker daemon` | ยังไม่เปิด Docker Desktop | เปิด Docker แล้วรอจนขึ้น Running |
| `ImportError: numpy` / `pandas` บน Lambda | build บน Windows โดยไม่ใช้ container | `sam build --use-container ...` ใหม่ |
| `AccessDeniedException` ตอนเรียก Bedrock | LabRole ไม่มีสิทธิ์ หรือแล็บบล็อก | ทำหัวข้อ 4.2 (แอปยังใช้ได้ด้วย fallback) |
| `ValidationException: ... on-demand throughput isn't supported` | ต้องใช้ inference profile | `--parameter-overrides BedrockModelId=us.amazon.nova-lite-v1:0` |
| `ResourceNotFoundException` ตอนเรียก Bedrock | Model ID ไม่มีใน region นี้ | ใช้ `amazon.nova-lite-v1:0` หรือ `us.amazon.nova-lite-v1:0` และ region `us-east-1` |
| `AccessDenied` ตอนสร้าง Function URL | แล็บบล็อก Lambda Function URL | แจ้งผู้ดูแลแล็บ พร้อมแนบผล `python3 scripts/preflight.py` |
| ไม่ได้รับอีเมล | ยังไม่ Confirm subscription / ติด Spam | ทำหัวข้อ 7 ใหม่ |
| `PendingConfirmation` | ยังไม่ยืนยันอีเมล | กดลิงก์ในอีเมล |
| Deploy ค้างนานมาก | Docker โหลด image ครั้งแรก + pip ติดตั้ง pandas | รอ 5–10 นาที หรือเช็คเน็ต |
| หน้าเว็บขึ้น `{"detail":"Not Found"}` | เปิด URL ไม่ครบ (`/` ปิดท้าย) | ใช้ `DashboardUrl` จาก Output ตรงๆ |
| ฟังก์ชัน timeout | วิเคราะห์ 10 หุ้นพร้อมกันช้า | ลดจำนวนหุ้น หรือเพิ่ม `Timeout` ใน template แล้ว deploy ใหม่ |
| อยากดู log | — | `aws logs tail /aws/lambda/ai-equity-copilot-app --follow` |

---

## 13. Checklist ก่อนวันเดโม

- [ ] Start Lab แล้ว `aws sts get-caller-identity` ผ่าน
- [ ] `python3 scripts/preflight.py` ผ่านทุกบริการหลัก
- [ ] `sam build --use-container -t template.learner-lab.yaml` ผ่าน
- [ ] `sam deploy --guided -t .aws-sam/build/template.yaml --config-env learnerlab` ผ่าน และจด `DashboardUrl` ไว้
- [ ] ยืนยันอีเมล SNS แล้ว (หรือรู้วิธีสร้าง subscription ใหม่)
- [ ] เพิ่ม `PTT.BK` + `NVDA` แล้วกดวิเคราะห์สำเร็จ (เห็นการ์ด + ต้นทุน AI)
- [ ] กดส่งรายงานแล้วได้รับอีเมลจริง
- [ ] เตรียม Workspace Code สำหรับเดโม เช่น `DEMO-CS446`
- [ ] เตรียม screenshot หน้าเว็บ + DynamoDB + อีเมล ไว้เป็น fallback ถ้าเน็ตห้องสอบมีปัญหา
- [ ] จด Region (`us-east-1`), Stack Name, และ Model ID ให้ตรงกับสไลด์
- [ ] ถ้า Bedrock ถูกบล็อก: เตรียมคำอธิบาย fallback + หลักฐานว่าแอปยังทำงานครบทุกบริการ

---

## 14. ข้อมูลสำหรับอาจารย์ / ผู้ดูแลแล็บ

ถ้าต้องขอเปิดสิทธิ์ Bedrock ใน `LabRole` ให้ส่งข้อความนี้:

> ขอเปิดสิทธิ์บน IAM role `LabRole` ของ Learner Lab:
> - Action: `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`
> - Resource: `arn:aws:bedrock:*::foundation-model/*` และ `arn:aws:bedrock:us-east-1:<AccountId>:inference-profile/*`
> - Trust policy ของ `LabRole` ต้องอนุญาต `lambda.amazonaws.com` (เพื่อให้ Lambda สวม role นี้ได้)
>
> โปรเจกต์: AI Equity Co-Pilot (ใช้ Lambda + DynamoDB + Bedrock + EventBridge + SNS ใน `us-east-1`)

ผลตรวจสอบก่อนส่งคำขอ (แนบได้): `python3 scripts/preflight.py`

---

## 15. ภาคผนวก: API และ Environment Variables

| Method | Path | Body | คำอธิบาย |
|---|---|---|---|
| `GET` | `/` | — | หน้าเว็บ Dashboard |
| `GET` | `/api/workspace/{id}` | — | Watchlist + ผลวิเคราะห์จาก cache + summary |
| `POST` | `/api/workspace/{id}/stocks` | `{"symbol":"PTT.BK"}` | เพิ่มหุ้น (สูงสุด 10) |
| `DELETE` | `/api/workspace/{id}/stocks/{symbol}` | — | ลบหุ้น |
| `POST` | `/api/workspace/{id}/persona` | `{"persona":"momentum"}` | เปลี่ยนโหมดนักลงทุน |
| `POST` | `/api/workspace/{id}/analyze` | `{"force_refresh":true}` | วิเคราะห์ทั้งพอร์ตแบบขนาน |
| `POST` | `/api/workspace/{id}/notify` | `{}` | ส่งรายงานเข้า SNS |

| Env var | ค่าเริ่มต้น | หน้าที่ |
|---|---|---|
| `PORTFOLIO_TABLE` | ชื่อตาราง DynamoDB | เก็บข้อมูล |
| `SNS_TOPIC_ARN` | ARN ของ topic | ปลายทางอีเมล |
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` | โมเดล AI |
| `CACHE_TTL_SECONDS` | `3600` | อายุ Smart Cache |
| `USD_TO_THB` | `36.0` | เรตแลกเปลี่ยนคำนวณต้นทุน |
| `MAX_SYMBOLS` | `10` | จำนวนหุ้นสูงสุดต่อพอร์ต |
