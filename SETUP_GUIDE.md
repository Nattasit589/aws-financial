# SETUP GUIDE — AWS Account (บัญชี AWS ปกติ)

คู่มือนี้สำหรับผู้ที่ใช้ **บัญชี AWS ส่วนตัว/บริษัท** ในการ deploy โปรเจกต์ **AI Equity Co-Pilot**
ใช้เวลาประมาณ **15 นาที** (ไม่รวมเวลารออีเมลยืนยัน SNS)

> ถ้าใช้ **AWS Academy Learner Lab** ให้ใช้ **[SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md)** แทน — ขั้นตอนต่างกันที่การสร้าง IAM role และ credential

---

## 0. ภาพรวมสิ่งที่จะถูกสร้าง

| บริการ | สิ่งที่เกิดขึ้นหลัง deploy |
|---|---|
| AWS Lambda + Function URL | ฟังก์ชัน `ai-equity-copilot-app` เสิร์ฟหน้าเว็บและ API ที่ URL หนึ่งเดียว |
| Amazon DynamoDB | ตาราง `ai-equity-copilot-PortfolioTable-xxxx` เก็บ Watchlist + Cache ผลวิเคราะห์ (TTL 1 ชม.) |
| Amazon Bedrock | เรียกโมเดล `amazon.nova-lite-v1:0` (สลับเป็น Claude Haiku ได้ผ่าน parameter) |
| Amazon EventBridge | กฎ `daily-market-close-analysis` ปลุก Lambda ทุกวันจันทร์–ศุกร์ 17:15 น. เวลาไทย |
| Amazon SNS | Topic + Email Subscription สำหรับรายงานสรุป |

ค่าใช้จ่ายระดับเดโมอยู่ใน Free Tier เป็นหลัก ส่วนที่คิดเงินจริงคือ Bedrock ประมาณ **0.002–0.01 บาทต่อหุ้น 1 ครั้ง**

---

## 1. สิ่งที่ต้องติดตั้งในเครื่อง

| โปรแกรม | ใช้ทำอะไร | วิธีติดตั้ง |
|---|---|---|
| **AWS CLI v2** | สั่งงาน AWS, ตั้งค่า credential | [Windows](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) / macOS `brew install awscli` |
| **AWS SAM CLI** | build + deploy ทั้ง stack | [คู่มือติดตั้ง](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) |
| **Python 3.12** | ให้ SAM build ตรงกับ Lambda runtime | python.org หรือ `pyenv` |
| **Docker Desktop** | ใช้กับ `sam build --use-container` | [docker.com](https://www.docker.com/products/docker-desktop/) — เปิดค้างไว้ตอน build |
| **Git** (ถ้าโคลนจาก repo) | ดึงโค้ด | git-scm.com |

ตรวจสอบ:

```bash
aws --version
sam --version
python --version
docker --version
```

> **Windows:** รันคำสั่งทั้งหมดใน **Git Bash**, **WSL** หรือ **PowerShell** (คู่มือนี้ใช้ syntax bash)

---

## 2. สร้าง IAM user และตั้งค่า CLI

### 2.1 สร้าง Access Key

1. เข้า AWS Console → **IAM** → **Users** → **Create user**
2. ตั้งชื่อ เช่น `equity-copilot-dev` → ไม่ต้องเปิด console access
3. **Attach policies directly** → `AdministratorAccess`
   - สำหรับบัญชีเรียน/แล็บใช้ AdministratorAccess เพื่อความเร็ว
   - บัญชีจริงควรจำกัดสิทธิ์: CloudFormation, Lambda, DynamoDB, SNS, IAM Role, S3 (เก็บ artifact), CloudWatch Logs, Bedrock
4. **Security credentials** → **Create access key** → เลือก *Application running outside AWS*
5. คัดลอก **Access key ID** และ **Secret access key** (เห็นครั้งเดียว)

### 2.2 ตั้งค่า CLI

```bash
aws configure
# AWS Access Key ID     : <access key>
# AWS Secret Access Key : <secret key>
# Default region name   : us-east-1
# Default output format : json
```

```bash
aws sts get-caller-identity
```

ต้องเห็น `Account`, `UserId`, `Arn` ถ้า error แปลว่า key ผิดหรือยังไม่ได้ตั้ง region

> **Region แนะนำ: `us-east-1`** — มีโมเดล Bedrock ครบและราคาถูก ถ้าเปลี่ยน region ต้องตรวจว่าโมเดลที่ใช้มีใน region นั้น

---

## 3. ตรวจสิทธิ์การใช้งานโมเดล Amazon Bedrock

1. เปิด **AWS Console** → Region `us-east-1`
2. เข้า **Amazon Bedrock** → ลองเรียกโมเดลใน **Playground** (`Amazon Nova Lite`)
   - บัญชี AWS ปกติรุ่นใหม่มักเปิดใช้ได้ทันทีเมื่อเรียกครั้งแรก ไม่ต้องกดขอสิทธิ์ที่หน้า Model access แบบเดิม
3. ทดสอบซ้ำด้วย CLI สคริปต์ (แนะนำ — ทดสอบเรียกโมเดลจริง 1 ครั้ง):

```bash
pip install boto3
python3 scripts/preflight.py
```

ถ้าได้ `AccessDeniedException` ให้ตรวจ:
- ผู้ใช้มีสิทธิ์ `bedrock:InvokeModel`
- ถ้าเป็น Anthropic Claude ต้องผ่าน first-time-use form ของ Anthropic
- region ตรงกับที่ deploy

---

## 4. เตรียมโค้ดโปรเจกต์

วางโฟลเดอร์ให้มีโครงสร้างนี้ (เปิด terminal ที่โฟลเดอร์นี้):

```
.
├── template.yaml                 # บัญชี AWS ปกติ (SAM สร้าง IAM role ให้)
├── template.learner-lab.yaml     # สำหรับ AWS Academy Learner Lab
├── requirements.txt
├── scripts/
│   └── preflight.py
├── src/
│   ├── app.py
│   ├── market_data.py
│   ├── analyzer.py
│   ├── db_and_notify.py
│   ├── requirements.txt
│   └── templates/
│       └── index.html
```

```bash
ls template.yaml
ls src/app.py src/templates/index.html scripts/preflight.py
```

> ห้ามลบ `src/requirements.txt` — SAM ใช้ไฟล์นี้ติดตั้งไลบรารีเข้า Lambda

---

## 5. Build แพ็กเกจ

```bash
sam build --use-container
```

- ครั้งแรกดาวน์โหลด Docker image `python3.12` + ติดตั้ง `fastapi`, `mangum`, `yfinance` (ดึง pandas/numpy) → ใช้เวลา **3–8 นาที**
- **ต้องเปิด Docker Desktop ค้างไว้** ไม่งั้นได้ `Cannot connect to the Docker daemon`
- ต้องมี `--use-container` เพราะ pandas/numpy เป็น binary ที่ผูกกับ OS — build บน Windows ตรงๆ แล้วขึ้น Lambda (Linux) จะได้ `ImportError: numpy`

สำเร็จแล้วจะเห็น:

```
Build Succeeded
Built Resources:
  Function: StockCopilotFunction
```

---

## 6. Deploy ขึ้น AWS

```bash
sam deploy --guided
```

ตอบคำถามดังนี้:

| คำถาม | ตอบ |
|---|---|
| Stack Name | `ai-equity-copilot` |
| AWS Region | `us-east-1` |
| Parameter AlertEmail | อีเมลจริงของคุณ |
| Parameter BedrockModelId | Enter (`amazon.nova-lite-v1:0`) |
| Parameter CacheTtlSeconds | Enter (3600) |
| Confirm changes before deploy | `N` |
| Allow SAM CLI IAM role creation | `Y` |
| Disable rollback | `N` |
| `... has no authentication. Is this okay?` | `y` |
| Create managed S3 bucket? (ถ้าถูกถาม) | `Y` |
| Save arguments to configuration file | `Y` |

สำเร็จจะเห็น `Successfully created/updated stack - ai-equity-copilot in us-east-1`

ดึงค่า Output:

```bash
aws cloudformation describe-stacks \
  --stack-name ai-equity-copilot \
  --query "Stacks[0].Outputs" \
  --output table
```

จะได้ `DashboardUrl`, `DynamoDBTableName`, `SNSTopicArn`

---

## 7. ยืนยันอีเมล SNS

1. เปิดกล่องจดหมายของ `AlertEmail`
2. หาอีเมลหัวข้อ **`AWS Notification - Subscription Confirmation`** (เช็ค Spam ด้วย)
3. กด **Confirm subscription**

ตรวจสถานะ:

```bash
aws sns list-subscriptions-by-topic --topic-arn "<SNSTopicArn>" \
  --query "Subscriptions[].SubscriptionArn" --output text
```

ถ้าได้ `PendingConfirmation` แปลว่ายังไม่กดยืนยัน — อีเมลรายงานจะยังไม่ถึง

---

## 8. ใช้งานหน้าเว็บ

เปิด `DashboardUrl` (ครั้งแรกช้า 1–3 วินาทีเพราะ cold start)

1. **Workspace Code** → พิมพ์รหัสพอร์ต เช่น `TEST-GROUP1` → **โหลดพอร์ต**
2. **สไตล์นักลงทุน** → *สายปันผลปลอดภัย* หรือ *สายเก็งกำไรสั้น*
3. **เพิ่มหุ้น** → หุ้นไทย `.BK` (`PTT.BK`, `ADVANC.BK`) / หุ้นสหรัฐฯ (`NVDA`, `AAPL`) — สูงสุด 10 ตัว
4. **บังคับดึงข้อมูลสด** → ติ๊กเพื่อข้าม Smart Cache (cache 1 ชม.)
5. **วิเคราะห์พอร์ตด้วย AI** → รอ 15–60 วินาที
6. **ส่งรายงานเข้าอีเมล (SNS)** → ส่งสรุปรอบล่าสุด
7. **Business & Cost** → ต้นทุน token จริง + เครื่องคิดเลขกำไร/จุดคุ้มทุน

หน้าจอมี **ตารางสรุปภาพรวมรายตัว** (สัญญาณ · เปลี่ยนแปลง · คะแนน · ความเสี่ยง) ก่อนการ์ดรายละเอียด

อ่านการ์ด: `Live Bedrock AI` (เรียกโมเดลใหม่) · `Smart Cache` (ผลภายใน 1 ชม.) · `Rule-based Fallback` (Bedrock ใช้ไม่ได้ ระบบสรุปด้วยกฎเทคนิคให้ก่อน) · `เสี่ยงต่ำ/ปานกลาง/สูง` (คำนวณจากความผันผวน/RSI/Bias/คะแนน) · `ข่าวบวก/กลาง/ลบ`

ทดสอบผ่าน API:

```bash
curl -X POST "<DashboardUrl>api/workspace/TEST-GROUP1/stocks" \
  -H "Content-Type: application/json" -d '{"symbol":"PTT.BK"}'

curl -X POST "<DashboardUrl>api/workspace/TEST-GROUP1/analyze" \
  -H "Content-Type: application/json" -d '{"force_refresh":true}'
```

> `DashboardUrl` มี `/` ปิดท้ายอยู่แล้ว ต่อด้วย `api/...` ได้เลย

---

## 9. ตรวจสอบว่าทั้ง 5 บริการทำงาน

```bash
aws lambda get-function-url-config --function-name ai-equity-copilot-app
aws dynamodb scan --table-name "<DynamoDBTableName>" --max-items 5
aws sns list-subscriptions-by-topic --topic-arn "<SNSTopicArn>"
aws events describe-rule --name daily-market-close-analysis
aws logs tail /aws/lambda/ai-equity-copilot-app --follow
```

ลำดับเดโม: **หน้าเว็บ → กดวิเคราะห์ → การ์ดผลลัพธ์ → DynamoDB → ส่งอีเมล → กล่องจดหมาย → EventBridge → CloudWatch**

---

## 10. แก้ไขโค้ดแล้ว deploy ซ้ำ

```bash
sam build --use-container && sam deploy
```

`sam deploy` รอบหลังไม่ต้อง `--guided` เพราะค่าถูกจำใน `samconfig.toml`
ถ้าแก้ชื่อ parameter หรือเพิ่ม resource ใหม่ ให้ `--guided` อีกครั้ง

ทดสอบบนเครื่อง (ไม่บังคับ):

```bash
pip install -r requirements.txt uvicorn
cd src
uvicorn app:app --reload --port 8000
# เปิด http://localhost:8000
```

> โหมด local เรียก DynamoDB/Bedrock/SNS จริงตาม credential — ถ้าไม่มี credential หน้าเว็บยังเปิดได้ แต่ปุ่มที่แตะฐานข้อมูลจะขึ้น error ภาษาไทย

---

## 11. ลบทรัพยากรหลังส่งงาน

```bash
sam delete --stack-name ai-equity-copilot
```

ลบทั้งหมด **รวมข้อมูล DynamoDB และ SNS subscription** (กู้คืนไม่ได้) — ตอบ `y` เมื่อถูกถามยืนยัน

---

## 12. แก้ปัญหาที่พบบ่อย

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| `sam build` error `Cannot connect to the Docker daemon` | ยังไม่เปิด Docker Desktop | เปิด Docker แล้วรอจน Running |
| Lambda ขึ้น `ImportError: numpy` / `pandas` | build บน Windows โดยไม่ใช้ container | `sam build --use-container` ใหม่ |
| Deploy error `Unable to upload artifact ... requirements.txt` | ไม่มี `src/requirements.txt` | ตรวจว่าไฟล์อยู่จริงใน `src/` |
| หน้าเว็บ `{"detail":"Not Found"}` | เปิด URL ไม่ครบ | ใช้ `DashboardUrl` จาก Output ตรงๆ |
| การ์ดขึ้น `Rule-based Fallback` | Bedrock เรียกไม่สำเร็จ | ดูหมายเหตุสีเหลืองบนการ์ด + รัน `python3 scripts/preflight.py` |
| `AccessDeniedException: bedrock:InvokeModel` | ไม่มีสิทธิ์/ยังไม่เปิดโมเดล | ทำข้อ 3 |
| `ResourceNotFoundException` ตอนเรียก Bedrock | Model ID ไม่มีใน region | เปลี่ยน `BedrockModelId` หรือเปลี่ยน region เป็น `us-east-1` |
| `ValidationException: on-demand throughput isn't supported` | ต้องใช้ inference profile | deploy ด้วย `--parameter-overrides BedrockModelId=us.amazon.nova-lite-v1:0` |
| การ์ดขึ้น `ไม่พบข้อมูลราคาของ XXX` | พิมพ์รหัสผิด/ลืม `.BK` | แก้รหัส (ระบบไม่ล่มทั้งพอร์ต) |
| ไม่ได้รับอีเมล SNS | ยังไม่ Confirm / ติด Spam | ทำข้อ 7 ใหม่ |
| ฟังก์ชัน timeout | วิเคราะห์หลายตัวเกิน 120 วินาที | ลดจำนวนหุ้น หรือเพิ่ม `Timeout` ใน `template.yaml` |
| ดู log ละเอียด | — | `aws logs tail /aws/lambda/ai-equity-copilot-app --follow` |

---

## 13. Checklist ก่อนวันเดโม

- [ ] `aws sts get-caller-identity` ทำงาน
- [ ] `python3 scripts/preflight.py` ผ่านทุกบริการหลัก
- [ ] `sam build --use-container` ผ่าน
- [ ] `sam deploy --guided` ผ่าน และได้ `DashboardUrl`
- [ ] ยืนยันอีเมล SNS แล้ว
- [ ] เพิ่ม `PTT.BK` + `NVDA` แล้ววิเคราะห์สำเร็จ
- [ ] กดส่งรายงานแล้วได้รับอีเมลจริง
- [ ] เตรียม Workspace Code สำหรับเดโม
- [ ] เตรียม screenshot หน้าเว็บ + DynamoDB + อีเมลเป็น fallback
- [ ] จด Stack Name / Region / Model ID ให้ตรงกับสไลด์

---

## 14. ภาคผนวก: API และ Environment Variables

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
