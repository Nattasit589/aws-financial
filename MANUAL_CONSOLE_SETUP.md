# 🖱️ MANUAL — ติดตั้งแบบคลิกเองทีละบริการ (AWS Console + CloudShell)

คู่มือนี้ทำทุกอย่าง **ด้วยมือทีละคลิกในหน้าเว็บ AWS Console** ไม่ใช้ CloudFormation/SAM เลย
ใช้ **AWS CloudShell** เฉพาะงานที่ต้องสั่งคำสั่ง (clone โค้ด, ติดตั้งไลบรารี, แพ็ก zip, อัปโหลด, ทดสอบ)

> **ใช้เมื่อไหร่:** อาจารย์ขอให้เดโมว่า "สร้างบริการเองเป็นทีละขั้น" / ต้องการเข้าใจว่าแต่ละบริการทำอะไร /
> ต้องการแก้เฉพาะบางบริการโดยไม่แตะ stack ทั้งก้อน
>
> ถ้าอยากได้แบบคำสั่งเดียวจบ ใช้ [QUICKSTART.md](QUICKSTART.md) หรือ [SETUP_LEARNER_LAB.md](SETUP_LEARNER_LAB.md) แทน

---

## ภาพรวม: 5 บริการที่ต้องสร้างเอง

| # | บริการ | ชื่อที่แนะนำ | หน้าที่ |
|---|---|---|---|
| 1 | **Amazon DynamoDB** | `portfolio` | เก็บ workspace, watchlist, ผลวิเคราะห์, TTL |
| 2 | **Amazon SNS** | `ai-equity-copilot-alerts` | ส่งอีเมลรายงาน |
| 3 | **AWS Lambda** | `ai-equity-copilot-app` | รัน FastAPI + วิเคราะห์หุ้น (runtime `python3.12`, handler `app.handler`) |
| 4 | **Lambda Function URL** | — | เปิดหน้าเว็บ HTTPS (ไม่ใช้ API Gateway) |
| 5 | **Amazon EventBridge** | `daily-market-close-analysis` | cron ปลุก Lambda ทุกวันจันทร์–ศุกร์ 17:15 น. ไทย |
| — | **Amazon Bedrock** | `amazon.nova-lite-v1:0` | เรียกผ่าน `boto3` จากในโค้ด ไม่ต้องสร้าง resource |

ค่าที่ต้องใช้เหมือนกันทุกขั้น (จดไว้):

```
Region          : us-east-1
Table            : portfolio
SNS Topic        : ai-equity-copilot-alerts
Lambda Function  : ai-equity-copilot-app
IAM Role         : LabRole            <-- Learner Lab สร้างให้แล้ว ห้ามสร้างใหม่
Runtime          : Python 3.12
Handler          : app.handler
Architecture     : x86_64
Timeout          : 120 วินาที
Memory           : 512 MB
```

---

## ขั้นที่ 0 — เตรียมแล็บ + CloudShell

1. เข้า **AWS Academy** → **Learner Lab** → กด **Start Lab** → รอจุดสถานะเป็น **สีเขียว**
2. กด **AWS** เพื่อเปิด Console แล้วตรวจมุมขวาบนว่าเป็น **N. Virginia (us-east-1)**
3. กดไอคอน **CloudShell** (`>_`) ที่แถบด้านบน แล้วรัน:

```bash
# ตรวจว่า credential ใช้ได้ (ไม่ต้อง aws configure ใน CloudShell)
aws sts get-caller-identity

# ไปทำงานใน /tmp (บ้านของ CloudShell มีที่ว่างแค่ ~1 GB)
export TMPDIR=/tmp
cd /tmp && git clone https://github.com/Nattasit589/aws-financial.git
cd aws-financial

# เก็บค่าที่ต้องใช้ซ้ำไว้ใน shell
export REGION=us-east-1
export FN=ai-equity-copilot-app
export TABLE=portfolio
```

---

## ขั้นที่ 1 — สร้าง DynamoDB Table (คลิกเอง)

1. Console → ค้นหา **DynamoDB** → **Create table**
2. กรอก:
   - **Table name:** `portfolio`
   - **Partition key:** `pk` ชนิด **String**
   - **Sort key:** `sk` ชนิด **String**
   - **Table settings:** เลือก **Customize settings**
   - **Capacity mode:** **On-demand** (ประหยัดที่สุดสำหรับเดโม)
3. เลื่อนลงไป **Secondary indexes** → ไม่ต้องสร้าง
4. เลื่อนลงไป **Encryption at rest** → ใช้ค่าเริ่มต้น (Owned by Amazon DynamoDB)
5. เปิด **TTL** (ในหน้าเดียวกัน หรือแก้ทีหลังที่แท็บ *Additional settings*) → **Turn on** → TTL attribute = `ttl`
6. กด **Create table** → รอสถานะ **Active** (~30 วินาที)

**ตรวจสอบ:**
```bash
aws dynamodb describe-table --table-name portfolio --region us-east-1 \
  --query "Table.{Status:TableStatus,Keys:KeySchema,TTL:TimeToLiveDescription}"
```

> ⚠️ ถ้าลืมเปิด TTL โปรแกรมยังทำงานได้ แต่ item เก่าจะไม่ถูกลบเอง (ค่าใช้จ่ายค่อยๆ โต)
> เปิดทีหลังได้ที่ DynamoDB → Tables → `portfolio` → **Additional settings** → **Time to Live (TTL)**

---

## ขั้นที่ 2 — สร้าง SNS Topic + อีเมล (คลิกเอง)

1. Console → ค้นหา **Simple Notification Service (SNS)** → **Topics** → **Create topic**
2. เลือก **Standard**, **Name:** `ai-equity-copilot-alerts`
3. กด **Create topic**
4. ในหน้า topic ที่สร้างเสร็จ กด **Create subscription**
   - **Protocol:** `Email`
   - **Endpoint:** อีเมลจริงของคุณ (เช่น `name@gmail.com`)
   - กด **Create subscription**
5. ไปที่กล่องจดหมาย → หัวข้อ **AWS Notification - Subscription Confirmation** → กด **Confirm subscription**

**ตรวจสอบ + เก็บ ARN ไว้ใช้ขั้นที่ 3:**
```bash
aws sns list-topics --region us-east-1
TOPIC_ARN=$(aws sns list-topics --region us-east-1 \
  --query "Topics[?contains(TopicArn,'ai-equity-copilot-alerts')].TopicArn" --output text)
echo "$TOPIC_ARN"
aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region us-east-1 \
  --query "Subscriptions[].{Protocol:Protocol,Endpoint:Endpoint,Pending:PendingConfirmation}"
```

> ถ้า `PendingConfirmation` ยังเป็น `true` อีเมลจะไม่ถูกส่ง — ต้องกดยืนยันก่อน

---

## ขั้นที่ 3 — สร้าง Lambda Function (คลิกเอง)

### 3.1 สร้างฟังก์ชัน

1. Console → ค้นหา **Lambda** → **Create function**
2. เลือก **Author from scratch**
   - **Function name:** `ai-equity-copilot-app`
   - **Runtime:** **Python 3.12**
   - **Architecture:** **x86_64**
   - **Permissions** → **Change default execution role** → **Use an existing role** → เลือก **`LabRole`**
     (Learner Lab ห้ามสร้าง role ใหม่ จึงต้องเลือกตัวที่มีอยู่)
3. กด **Create function**

### 3.2 ตั้งค่า General configuration

แท็บ **Configuration** → **General configuration** → **Edit**
- **Memory:** `512` MB
- **Timeout:** `2` นาที 0 วินาที (120 วินาที)
- **Handler:** อยู่ที่แท็บ **Runtime settings** → **Edit** → `app.handler`
- กด **Save**

### 3.3 ใส่ Environment variables

**Configuration** → **Environment variables** → **Edit** → **Add environment variable** (ใส่ทีละตัว)

| Key | Value |
|---|---|
| `PORTFOLIO_TABLE` | `portfolio` |
| `SNS_TOPIC_ARN` | ARN จากขั้นที่ 2 |
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` |
| `CACHE_TTL_SECONDS` | `3600` |
| `USD_TO_THB` | `36.0` |
| `MAX_SYMBOLS` | `10` |

> ถ้าแล็บบล็อกโมเดลนี้ ให้เปลี่ยนเป็น `us.amazon.nova-lite-v1:0` (cross-region inference profile)

### 3.4 แพ็กโค้ด + อัปโหลด (ทำใน CloudShell)

ตอนสร้างฟังก์ชัน Lambda โค้ดจะยังว่าง ต้องเอา zip ที่มีไลบรารีครบขึ้นไป:

```bash
cd /tmp/aws-financial

# 1) ติดตั้ง Python 3.12 ให้ตรงกับ runtime (CloudShell มี 3.12 ให้ติดตั้งได้)
sudo dnf install -y python3.12 python3.12-pip

# 2) ติดตั้งไลบรารีลงโฟลเดอร์ build (x86_64 Linux ตรงกับ Lambda)
rm -rf /tmp/build && mkdir -p /tmp/build
python3.12 -m pip install -r src/requirements.txt -t /tmp/build --quiet

# 3) คัดลอกโค้ดโปรแกรมทับลงไป (ไม่ทับไลบรารี)
cp -r src/app.py src/market_data.py src/analyzer.py src/db_and_notify.py src/templates /tmp/build/

# 4) แพ็กเป็น zip (วางไฟล์ไว้ที่ root ของ zip)
rm -f /tmp/function.zip
cd /tmp/build && zip -r /tmp/function.zip . -x "*.pyc" -x "__pycache__/*" --quiet
ls -lh /tmp/function.zip

# 5) อัปโหลดขึ้น Lambda
aws lambda update-function-code \
  --function-name ai-equity-copilot-app \
  --zip-file fileb:///tmp/function.zip \
  --region us-east-1 \
  --query "{CodeSize:CodeSize,State:State,LastUpdateStatus:LastUpdateStatus}"
```

> **ถ้า `zip` ไม่มีใน CloudShell** ใช้: `cd /tmp/build && python3.12 -m zipfile -c /tmp/function.zip .`
>
> **ถ้า zip ใหญ่เกิน 50 MB** (อัปโหลดตรงไม่ผ่าน) ให้วางบน S3 แล้วสั่ง:
> `aws lambda update-function-code --function-name ai-equity-copilot-app --s3-bucket <bucket> --s3-key function.zip`

**ตรวจสอบว่าโค้ดรันได้ (ไม่ต้องมี URL):**
```bash
aws lambda invoke --function-name ai-equity-copilot-app \
  --region us-east-1 \
  --payload '{"source":"aws.events","detail-type":"Scheduled Event","action":"scheduled"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/scheduled.json && cat /tmp/scheduled.json
```
ผลที่ดีคือได้ JSON มี `"ok"` (ถ้ายังไม่มี workspace จะได้ `"workspaces": 0` — ปกติ)

> หมายเหตุ: การ invoke แบบ EventBridge นี้จะ **ไม่ส่งอีเมล** ถ้ายังไม่มี workspace ในตาราง

---

## ขั้นที่ 4 — เปิด Lambda Function URL (คลิกเอง)

1. ในหน้า Lambda function → แท็บ **Configuration** → **Function URL** → **Create function URL**
2. **Auth type:** **NONE** (หน้าเว็บเป็น public — เหมาะกับเดโมในรายวิชา)
3. **Configure cross-origin resource sharing (CORS)** → เปิด
   - **Allow origin:** `*`
   - **Allow headers:** `*`
   - **Allow methods:** `*`
   - **Max age:** `86400`
4. กด **Save** → คัดลอก **Function URL** (ลงท้าย `.lambda-url.us-east-1.on.aws/`)

**ตรวจสอบจาก CloudShell:**
```bash
URL=$(aws lambda get-function-url-config --function-name ai-equity-copilot-app \
  --region us-east-1 --query FunctionUrl --output text)
echo "$URL"
curl -s "$URL" | head -c 200                 # ต้องได้ HTML ของหน้า Dashboard
curl -s "${URL}api/workspace/GROUP7-DEMO"     # ต้องได้ JSON ของ workspace (ไม่ต้องมีอยู่จริงก็ได้)
```

> ถ้าเปิด URL แล้วได้ `403 Forbidden` ให้ตรวจว่า Auth type เป็น `NONE`
> ถ้าได้ `500` ให้ดู **Monitor → View CloudWatch logs** (สาเหตุที่พบบ่อย: ยังไม่ได้อัปโหลด zip / env var ผิดชื่อ)

---

## ขั้นที่ 5 — สร้าง EventBridge Rule (คลิกเอง)

1. Console → ค้นหา **EventBridge** → **Rules** → **Create rule**
2. กรอก:
   - **Name:** `daily-market-close-analysis`
   - **Event bus:** `default`
   - **Rule type:** **Schedule**
   - **Schedule pattern:** เลือก **A schedule that runs at a regular rate** ไม่ได้ — ต้องเลือก **Cron expression** แล้วใส่:
     ```
     cron(15 10 ? * MON-FRI *)
     ```
     (10:15 UTC = 17:15 น. เวลาไทย, จันทร์–ศุกร์)
3. **Select targets** → **Target types:** AWS service → **Target:** **Lambda function** → เลือก `ai-equity-copilot-app`
4. กด **Create rule**

**สิ่งที่ต้องเพิ่มด้วยมือ (สำคัญ):** EventBridge ต้องได้รับสิทธิ์เรียก Lambda

```bash
# อนุญาตให้ EventBridge (events.amazonaws.com) เรียกฟังก์ชันนี้
RULE_ARN=$(aws events describe-rule --name daily-market-close-analysis \
  --region us-east-1 --query Arn --output text)

aws lambda add-permission \
  --function-name ai-equity-copilot-app \
  --statement-id AllowEventBridgeDailyMarketClose \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "$RULE_ARN" \
  --region us-east-1
```

**ทดสอบว่า rule ถูกผูกกับฟังก์ชันถูกตัว:**
```bash
aws events list-targets-by-rule --rule daily-market-close-analysis \
  --region us-east-1 --query "Targets[].{Id:Id,Arn:Arn}"
```

> ระหว่างทำแล็บ ปิด rule ไว้ก่อนได้ (Rules → เลือก rule → **Disable**) กัน Lambda ถูกปลุกและกินเครดิต
> ถ้าไม่ใส่ `add-permission` rule จะยิงแล้วขึ้น error `AccessDeniedException` ใน CloudWatch

---

## ขั้นที่ 6 — ทดสอบทั้งระบบด้วยมือ

1. เปิด **Function URL** ในเบราว์เซอร์
2. พิมพ์ Workspace Code เช่น `GROUP7-DEMO` → กด **โหลดพอร์ต**
3. เพิ่มหุ้น `PTT.BK`, `ADVANC.BK`, `NVDA` → กด **วิเคราะห์พอร์ตด้วย AI**
4. ตรวจว่าเขียนลง DynamoDB จริง:
   ```bash
   aws dynamodb scan --table-name portfolio --region us-east-1 \
     --max-items 5 --query "Items[].{pk:pk.s,sk:sk.s}"
   ```
5. กด **ส่งรายงานเข้าอีเมล (SNS)** → เปิดกล่องจดหมาย (ถ้าเป็นครั้งแรกต้อง Confirm subscription แล้ว)
6. ดู log ย้อนหลัง:
   ```bash
   aws logs tail "/aws/lambda/ai-equity-copilot-app" --since 10m --region us-east-1
   ```

---

## ขั้นที่ 7 — ลบทุกอย่างด้วยมือ (สำคัญ: เรียงตามลำดับ)

ลบย้อนศร เพื่อไม่ให้มีอะไรค้าง (Learner Lab คิดเครดิตแม้ไม่เรียกใช้):

```bash
# 1) ปิด/ลบ EventBridge rule
aws events remove-targets --rule daily-market-close-analysis --ids 1 --region us-east-1
aws events delete-rule --name daily-market-close-analysis --region us-east-1

# 2) ลบ Function URL แล้วลบฟังก์ชัน
aws lambda delete-function-url-config --function-name ai-equity-copilot-app --region us-east-1
aws lambda delete-function --function-name ai-equity-copilot-app --region us-east-1

# 3) ลบ SNS subscription + topic
aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region us-east-1 \
  --query "Subscriptions[].SubscriptionArn" --output text | tr '\t' '\n' | while read -r s; do
    aws sns unsubscribe --subscription-arn "$s"; done
aws sns delete-topic --topic-arn "$TOPIC_ARN" --region us-east-1

# 4) ลบตาราง DynamoDB
aws dynamodb delete-table --table-name portfolio --region us-east-1
```

หรือคลิกเองก็ได้: EventBridge → Rules → Delete, Lambda → Delete, SNS → Delete topic, DynamoDB → Delete table

---

## ตารางเทียบ: ทำมือ vs ใช้ Template

| หัวข้อ | ทำมือ (ไฟล์นี้) | ใช้ SAM template |
|---|---|---|
| จำนวนครั้งที่คลิก | ~25 ครั้ง | 1 คำสั่ง |
| โอกาสตั้งค่าผิด | สูง (env var / handler / role) | ต่ำ |
| เข้าใจว่าแต่ละบริการทำอะไร | ดีมาก | ปานกลาง |
| ทำซ้ำได้เหมือนเดิมทุกครั้ง | ยาก | ง่าย (template เป็นโค้ด) |
| เหมาะกับ | เดโม/อธิบายอาจารย์ | ส่งงานจริง |

---

## Troubleshooting — อาการที่เจอบ่อยตอนทำมือ

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| `AccessDenied` ตอนสร้าง Lambda (role) | Learner Lab ห้ามสร้าง role | เลือก **Use an existing role → LabRole** |
| หน้าเว็บ 500 / log ว่า `ModuleNotFoundError: fastapi` | zip ไม่มีไลบรารี หรือวางไฟล์ผิดชั้น | build zip ใหม่จากขั้น 3.4 (ไฟล์ `app.py` ต้องอยู่ที่ **root ของ zip**) |
| log ว่า `Unable to import module 'app'` | Handler ผิด | Runtime settings → Handler = `app.handler` |
| `403 Forbidden` ที่ Function URL | Auth type ไม่ใช่ NONE หรือ rule permission ขาด | ตั้ง Auth = `NONE` / ใส่ `add-permission` |
| `ImportError: numpy` | แพ็กบน OS อื่น (macOS/Windows) | build บน CloudShell (Linux x86_64) ตามขั้น 3.4 |
| NodejsRuntime error ตอน invoke | เลือก runtime ผิด | Runtime = **Python 3.12** |
| ไม่มีอีเมลมา | ยังไม่ confirm subscription / `SNS_TOPIC_ARN` ผิด | ดู `PendingConfirmation` และ env var |
| EventBridge ไม่ยิง | rule disabled / ไม่มี `add-permission` | เปิด rule + ตรวจ CloudWatch error |
| `ServiceException: Bedrock ... AccessDenied` | แล็บบล็อกสิทธิ์ Bedrock | ใช้ `us.amazon.nova-lite-v1:0` หรือปล่อยให้ fallback ทำงาน |

---

## Checklist ก่อนปิดเครื่อง

- [ ] DynamoDB `portfolio` สถานะ Active + TTL เปิด (`ttl`)
- [ ] SNS topic + subscription ยืนยันอีเมลแล้ว (`PendingConfirmation: false`)
- [ ] Lambda `ai-equity-copilot-app` runtime 3.12, handler `app.handler`, 512 MB, 120 วิ, role `LabRole`
- [ ] Environment variables ครบ 6 ตัว
- [ ] อัปโหลด zip แล้ว `LastUpdateStatus: Successful`
- [ ] Function URL auth = NONE + CORS เปิด และ `curl` ได้ HTML
- [ ] EventBridge rule `daily-market-close-analysis` + target + `add-permission`
- [ ] ทดสอบ analyze 1 รอบ เขียนลง DynamoDB จริง
- [ ] ลบทรัพยากรครบ 4 อย่างเมื่อเลิกใช้ (ขั้นที่ 7)
