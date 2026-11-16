# 🖱️ MANUAL — ติดตั้งแบบคลิกเองทีละบริการ (AWS Console + CloudShell)

คู่มือนี้ทำทุกอย่าง **ด้วยมือทีละคลิกในหน้าเว็บ AWS Console** ไม่ใช้ CloudFormation/SAM เลย
ใช้ **AWS CloudShell** เฉพาะงานที่ต้องสั่งคำสั่ง (clone โค้ด, ติดตั้งไลบรารี, แพ็ก zip ขึ้น S3, ทดสอบ)

> **ใช้เมื่อไหร่:** อาจารย์ขอให้เดโมว่า "สร้างบริการเองเป็นทีละขั้น" / ต้องการเข้าใจว่าแต่ละบริการทำอะไร / ต้องการแก้เฉพาะบางบริการโดยไม่แตะ stack ทั้งก้อน
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

```text
Region          : us-east-1
Table           : portfolio
SNS Topic       : ai-equity-copilot-alerts
Lambda Function : ai-equity-copilot-app
IAM Role        : LabRole            <-- Learner Lab สร้างให้แล้ว ห้ามสร้างใหม่
Runtime         : Python 3.12
Handler         : app.handler
Architecture    : x86_64
Timeout         : 120 วินาที (2 นาที)
Memory          : 512 MB
```

---

## ขั้นที่ 0 — เตรียมแล็บ + CloudShell

1. เข้า **AWS Academy** → **Learner Lab** → กด **Start Lab** → รอจุดสถานะเป็น **สีเขียว**
2. กด **AWS** เพื่อเปิด Console แล้วตรวจมุมขวาบนว่าเป็น **N. Virginia (us-east-1)**
3. กดไอคอน **CloudShell** (`>_`) ที่แถบด้านบน แล้วรัน:

```bash
# ตรวจว่า credential ใช้ได้ (ไม่ต้อง aws configure ใน CloudShell)
aws sts get-caller-identity

# ไปทำงานใน /tmp ทั้งโค้ดและ cache (บ้านของ CloudShell มีที่ว่างแค่ ~1 GB)
export TMPDIR=/tmp PIP_CACHE_DIR=/tmp/pip-cache
rm -rf /tmp/aws-financial
cd /tmp && git clone https://github.com/Nattasit589/aws-financial.git
cd aws-financial

# เก็บค่าที่ต้องใช้ซ้ำไว้ใน shell
export REGION=us-east-1
export FN=ai-equity-copilot-app
export TABLE=portfolio
```

---

## ขั้นที่ 1 — สร้าง DynamoDB Table (คลิกเอง)

1. Console → ค้นหา **DynamoDB** → เมนูซ้าย **Tables** → **Create table**
2. กรอก:
   - **Table name:** `portfolio`
   - **Partition key:** `pk` ชนิด **String**
   - **Sort key:** `sk` ชนิด **String**
   - **Table settings:** เลือก **Customize settings**
   - **Capacity mode:** เลือก **On-demand** (ประหยัดที่สุดสำหรับเดโม)
3. เลื่อนลงไป **Secondary indexes** → ไม่ต้องสร้าง
4. เลื่อนลงไป **Encryption at rest** → ใช้ค่าเริ่มต้น (Owned by Amazon DynamoDB)
5. กดปุ่มสีส้ม **Create table** → รอสถานะเปลี่ยนเป็น **Active** (~15–30 วินาที)
6. **เปิดระบบลบข้อมูลเก่าอัตโนมัติ (TTL):**
   - คลิกเข้าไปที่ชื่อตาราง `portfolio` → เลือกแท็บ **Additional settings**
   - เลื่อนไปที่หัวข้อ **Time to Live (TTL)** → กด **Turn on**
   - ช่อง **TTL attribute name** พิมพ์ `ttl` → กด **Turn on TTL**

**ตรวจสอบใน CloudShell:**

```bash
aws dynamodb describe-table --table-name portfolio --region us-east-1 \
  --query "Table.{Status:TableStatus,Keys:KeySchema}"
aws dynamodb describe-time-to-live --table-name portfolio --region us-east-1
```

> ⚠️ ถ้าลืมเปิด TTL โปรแกรมยังทำงานได้ แต่ cache เก่าจะไม่ถูกลบเองตามเวลา

---

## ขั้นที่ 2 — สร้าง SNS Topic + อีเมล (คลิกเอง)

1. Console → ค้นหา **Simple Notification Service (SNS)** → เมนูซ้าย **Topics** → **Create topic**
2. เลือก **Type:** **Standard** *(ห้ามเลือก FIFO)* และตั้ง **Name:** `ai-equity-copilot-alerts`
3. กด **Create topic** (คัดลอกค่า **ARN** บนหน้าจอเก็บไว้ใช้ในขั้นที่ 3)
4. ในหน้า topic ที่สร้างเสร็จ กดปุ่ม **Create subscription**
   - **Protocol:** `Email`
   - **Endpoint:** อีเมลจริงของคุณ (เช่น `name@gmail.com`)
   - กด **Create subscription**
5. ไปที่กล่องจดหมายอีเมล (รวมถึงโฟลเดอร์ Spam) → เปิดหัวข้อ **AWS Notification - Subscription Confirmation** → กด **Confirm subscription**

**ตรวจสอบ + เก็บ ARN ไว้ใช้ขั้นที่ 3:**

```bash
TOPIC_ARN=$(aws sns list-topics --region us-east-1 \
  --query "Topics[?contains(TopicArn,'ai-equity-copilot-alerts')].TopicArn" --output text)
echo "$TOPIC_ARN"

aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region us-east-1 \
  --query "Subscriptions[].{Protocol:Protocol,Endpoint:Endpoint,SubArn:SubscriptionArn}"
```

> ถ้าช่อง `SubArn` ยังขึ้นคำว่า `PendingConfirmation` อีเมลจะไม่ถูกส่ง — ต้องกดยืนยันในอีเมลก่อน

---

## ขั้นที่ 3 — สร้าง Lambda Function (คลิกเอง)

### 3.1 สร้างฟังก์ชัน
1. Console → ค้นหา **Lambda** → **Create function**
2. เลือก **Author from scratch**
   - **Function name:** `ai-equity-copilot-app`
   - **Runtime:** **Python 3.12**
   - **Architecture:** **x86_64**
   - **Permissions** → กดขยาย **Change default execution role** → เลือก **Use an existing role** → เลือก **`LabRole`** *(Learner Lab ห้ามสร้าง role ใหม่)*
3. กด **Create function**

### 3.2 ตั้งค่า General configuration และ Handler
- ไปที่แท็บ **Configuration** → เมนูซ้าย **General configuration** → **Edit**
  - **Memory:** `512` MB
  - **Timeout:** `2` min `0` sec (120 วินาที) → กด **Save**
- กลับไปที่แท็บ **Code** → เลื่อนลงมาที่กล่อง **Runtime settings** → **Edit**
  - **Handler:** แก้จาก `lambda_function.lambda_handler` เป็น `app.handler` → กด **Save**

### 3.3 ใส่ Environment variables
ไปที่แท็บ **Configuration** → เมนูซ้าย **Environment variables** → **Edit** → **Add environment variable** (ใส่ครบทั้ง 6 ตัว + 2 ตัวเลือกถ้าจะใช้ AI สำรอง):

| Key | Value |
|---|---|
| `PORTFOLIO_TABLE` | `portfolio` |
| `SNS_TOPIC_ARN` | วางค่า ARN ของ SNS จากขั้นที่ 2 |
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` |
| `CACHE_TTL_SECONDS` | `3600` |
| `USD_TO_THB` | `36.0` |
| `MAX_SYMBOLS` | `10` |
| `GEMINI_API_KEY` | *(ไม่บังคับ)* key จาก Google AI Studio — เปิดใช้ AI สำรองเมื่อ Bedrock ถูกบล็อกสิทธิ |
| `GEMINI_MODEL_ID` | `gemini-3.5-flash-lite` (แก้เป็น `gemini-3.8-flash` ได้ถ้าโมเดลนี้ไม่พร้อม) |

> ถ้าแล็บบล็อกโมเดลนี้ ให้ลองเปลี่ยนเป็น `us.amazon.nova-lite-v1:0` ถ้ายังไม่ได้และมี `GEMINI_API_KEY` ระบบจะใช้ **AI สำรอง Google Gemini** ก่อน ถ้าไม่มี key จึงสลับเข้า **Rule-based fallback** อัตโนมัติ (ป้ายบนการ์ดบอกว่าผลมาจากชั้นไหน)

### 3.4 แพ็กโค้ด + อัปโหลดผ่าน S3 (ทำใน CloudShell)
เนื่องจากไฟล์ `.zip` เมื่อรวมไลบรารี `fastapi` + `yfinance` + `pandas` จะมีขนาดประมาณ **65.5 MB** (เกินลิมิต 50 MB ของการอัปโหลดตรง) จึงต้องพักไฟล์ผ่านถัง S3 ก่อนอัปโหลดเข้า Lambda:

```bash
export TMPDIR=/tmp PIP_CACHE_DIR=/tmp/pip-cache
cd /tmp/aws-financial

# 1) ติดตั้ง Python 3.12 และ zip ให้ตรงกับ runtime บน Lambda
sudo dnf install -y python3.12 python3.12-pip zip

# 2) ติดตั้งไลบรารีลงโฟลเดอร์ /tmp/build (ใช้ --no-cache-dir กันพื้นที่โฮมเต็ม)
rm -rf /tmp/build && mkdir -p /tmp/build
python3.12 -m pip install --no-cache-dir -r src/requirements.txt -t /tmp/build --quiet

# 3) คัดลอกโค้ดโปรแกรมทั้งหมดจาก src/ ทับลงไป
cp -r src/* /tmp/build/

# 4) แพ็กเป็น zip (วางไฟล์ไว้ที่ root ของ zip)
rm -f /tmp/function.zip
cd /tmp/build && zip -r /tmp/function.zip . -x "*.pyc" -x "__pycache__/*" --quiet
ls -lh /tmp/function.zip

# 5) ส่งไฟล์ .zip ขึ้นถัง S3 ชั่วคราว แล้วสั่งอัปเดตเข้า Lambda (หรือนำลิงก์ S3 ไปกด Upload from S3 บนหน้าเว็บก็ได้)
ACC_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ai-equity-manual-${ACC_ID}"
aws s3 mb "s3://${BUCKET}" --region us-east-1 2>/dev/null || true
aws s3 cp /tmp/function.zip "s3://${BUCKET}/function.zip"

aws lambda update-function-code \
  --function-name ai-equity-copilot-app \
  --s3-bucket "$BUCKET" \
  --s3-key function.zip \
  --region us-east-1 \
  --query "{CodeSize:CodeSize,State:State,LastUpdateStatus:LastUpdateStatus}"

# รอจน Lambda แตกไฟล์โค้ดเสร็จสมบูรณ์ก่อนทดสอบ
aws lambda wait function-updated --function-name ai-equity-copilot-app --region us-east-1
echo "อัปเดตโค้ดขึ้น Lambda สำเร็จ!"
```

**ตรวจสอบว่าโค้ดรันได้จริง (ยังไม่ต้องมี URL):**

```bash
aws lambda invoke --function-name ai-equity-copilot-app \
  --region us-east-1 \
  --payload '{"source":"aws.events","detail-type":"Scheduled Event","action":"scheduled"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/scheduled.json && cat /tmp/scheduled.json
```

ผลที่ดีคือได้ JSON มี `"ok"` (ถ้ายังไม่มี workspace จะได้ `"workspaces": 0` — ถือว่าปกติ)

---

## ขั้นที่ 4 — เปิด Lambda Function URL (คลิกเอง)

1. ในหน้าฟังก์ชัน Lambda → แท็บ **Configuration** → เมนูซ้าย **Function URL** → **Create function URL**
2. **Auth type:** เลือก **NONE** (เพื่อให้เปิดหน้าเว็บผ่านเบราว์เซอร์ได้)
3. ติ๊กถูกเปิด **Configure cross-origin resource sharing (CORS)**:
   - **Allow origin:** `*`
   - **Allow headers:** `*`
   - **Allow methods:** เลือก `*` (หรือติ๊กครบทุกตัว)
   - **Max age:** `86400`
4. กด **Save** → คัดลอกลิงก์ **Function URL** (ลงท้าย `.lambda-url.us-east-1.on.aws/`)

**ตรวจสอบจาก CloudShell:**

```bash
URL=$(aws lambda get-function-url-config --function-name ai-equity-copilot-app \
  --region us-east-1 --query FunctionUrl --output text)
echo "$URL"
curl -s "$URL" | head -c 200                 # ต้องได้ HTML ของหน้า Dashboard
curl -s "${URL}api/workspace/GROUP7-DEMO"     # ต้องได้ JSON ของ workspace
```

---

## ขั้นที่ 5 — สร้าง EventBridge Rule (คลิกเอง)

1. Console → ค้นหา **EventBridge** → เมนูซ้ายใต้ Buses คลิก **Rules** → **Create rule**
2. กรอกหน้าแรก:
   - **Name:** `daily-market-close-analysis`
   - **Event bus:** `default`
   - **Rule type:** เลือก **Schedule**
   - ⚠️ **สำคัญมากสำหรับ Learner Lab:** ให้กดปุ่มสีขาว **Continue to create rule** *(ห้ามกดปุ่มสีส้ม Continue in EventBridge Scheduler เพราะตัว Scheduler ใหม่จะบังคับสร้าง IAM Role ซึ่งติดสิทธิ์ของ Learner Lab)*
3. หน้า **Define schedule**:
   - เลือก **A fine-grained schedule... (Cron expression)** แล้วกรอกค่า `15` `10` `?` `*` `MON-FRI` `*` เพื่อให้ได้:
     ```text
     cron(15 10 ? * MON-FRI *)
     ```
     *(10:15 UTC = 17:15 น. เวลาไทย ทุกวันจันทร์–ศุกร์)* → กด **Next**
4. หน้า **Select target(s)**:
   - **Target types:** เลือก **AWS service**
   - **Select a target:** เลือก **Lambda function** → ช่อง Function เลือก `ai-equity-copilot-app`
5. กด **Next** → **Next** → **Create rule**

**ตรวจสอบสิทธิ์การเรียก Lambda (ปกติหน้าเว็บผูกให้อัตโนมัติ แต่รันย้ำเพื่อความชัวร์ได้):**

```bash
RULE_ARN=$(aws events describe-rule --name daily-market-close-analysis \
  --region us-east-1 --query Arn --output text)

aws lambda add-permission \
  --function-name ai-equity-copilot-app \
  --statement-id AllowEventBridgeDailyMarketClose \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "$RULE_ARN" \
  --region us-east-1 2>/dev/null || echo "ผูกสิทธิ์ไว้เรียบร้อยแล้ว"

aws events list-targets-by-rule --rule daily-market-close-analysis \
  --region us-east-1 --query "Targets[].{Id:Id,Arn:Arn}"
```

---

## ขั้นที่ 6 — ทดสอบทั้งระบบด้วยมือ

1. เปิดลิงก์ **Function URL** ในเบราว์เซอร์
2. พิมพ์ Workspace Code เช่น `GROUP7-DEMO` → กด **โหลดพอร์ต**
3. เพิ่มหุ้น `PTT.BK`, `ADVANC.BK`, `NVDA` → กด **วิเคราะห์พอร์ตด้วย AI**
4. ตรวจว่าข้อมูลเขียนลง DynamoDB จริง:
   ```bash
   aws dynamodb scan --table-name portfolio --region us-east-1 \
     --max-items 5 --query "Items[].{pk:pk.S,sk:sk.S}"
   ```
5. กด **ส่งรายงานเข้าอีเมล (SNS)** → เปิดเช็กกล่องจดหมายอีเมลของคุณ
6. ดู Log การทำงานย้อนหลัง:
   ```bash
   aws logs tail "/aws/lambda/ai-equity-copilot-app" --since 10m --region us-east-1
   ```

---

## ขั้นที่ 7 — ลบทุกอย่างเมื่อเลิกใช้ (สำคัญ: เรียงตามลำดับย้อนศร)

```bash
# 1) ดึงรหัส Target ID จริงมาถอดออกจาก EventBridge rule แล้วลบ rule
TARGET_IDS=$(aws events list-targets-by-rule --rule daily-market-close-analysis \
  --region us-east-1 --query "Targets[].Id" --output text)
if [ -n "$TARGET_IDS" ]; then
  aws events remove-targets --rule daily-market-close-analysis --ids $TARGET_IDS --region us-east-1
fi
aws events delete-rule --name daily-market-close-analysis --region us-east-1

# 2) ลบ Function URL และลบฟังก์ชัน Lambda
aws lambda delete-function-url-config --function-name ai-equity-copilot-app --region us-east-1 2>/dev/null || true
aws lambda delete-function --function-name ai-equity-copilot-app --region us-east-1

# 3) ลบ SNS subscription + topic
TOPIC_ARN=$(aws sns list-topics --region us-east-1 \
  --query "Topics[?contains(TopicArn,'ai-equity-copilot-alerts')].TopicArn" --output text)
if [ -n "$TOPIC_ARN" ]; then
  aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region us-east-1 \
    --query "Subscriptions[].SubscriptionArn" --output text | tr '\t' '\n' | while read -r s; do
      [ "$s" != "PendingConfirmation" ] && [ -n "$s" ] && aws sns unsubscribe --subscription-arn "$s"
    done
  aws sns delete-topic --topic-arn "$TOPIC_ARN" --region us-east-1
fi

# 4) ลบตาราง DynamoDB + ถัง S3 ชั่วคราว + ไฟล์ใน /tmp
aws dynamodb delete-table --table-name portfolio --region us-east-1
ACC_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 rb "s3://ai-equity-manual-${ACC_ID}" --force 2>/dev/null || true
rm -rf /tmp/aws-financial /tmp/build /tmp/function.zip /tmp/pip-cache
```

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
| `AccessDenied` ตอนสร้าง Lambda หรือ EventBridge | Learner Lab ห้ามสร้าง role ใหม่ | Lambda เลือก **LabRole** / EventBridge กดปุ่มสีขาว **Continue to create rule** |
| อัปโหลด zip ไม่ผ่าน (`RequestEntityTooLarge`) | ไฟล์ zip ใหญ่เกิน 50 MB (~65.5 MB) | อัปโหลดผ่านถัง S3 ตามขั้น 3.4 |
| `No space left on device` ตอน pip install | พื้นที่โฮม 1 GB เต็มเพราะ cache | ตั้ง `PIP_CACHE_DIR=/tmp/pip-cache` และใส่ `--no-cache-dir` |
| หน้าเว็บ 500 / `ModuleNotFoundError: fastapi` | zip ไม่มีไลบรารี หรือวางไฟล์ผิดชั้น | build zip ใหม่ตามขั้น 3.4 (`app.py` ต้องอยู่ที่ root ของ zip) |
| Log ว่า `Unable to import module 'app'` | Handler ยังเป็นค่าเริ่มต้น | Runtime settings → Handler = `app.handler` |
| `403 Forbidden` ที่ Function URL | Auth type ไม่ใช่ NONE | ตั้ง Auth type = `NONE` |
| ไม่มีอีเมลส่งมา | ยังไม่ได้กดยืนยันในอีเมล / ใส่ ARN ผิด | เช็กอีเมลกด Confirm subscription และตรวจค่า `SNS_TOPIC_ARN` |

---

## Checklist ก่อนปิดเครื่อง

- [ ] DynamoDB `portfolio` สถานะ Active + เปิด TTL (`ttl`)
- [ ] SNS topic + subscription ยืนยันอีเมลแล้ว
- [ ] Lambda `ai-equity-copilot-app` runtime 3.12, handler `app.handler`, 512 MB, 120 วิ, role `LabRole`
- [ ] Environment variables ครบทั้ง 6 ตัว (+ `GEMINI_API_KEY`/`GEMINI_MODEL_ID` ถ้าจะใช้ AI สำรอง)
- [ ] อัปโหลด zip ผ่าน S3 แล้วสถานะ `LastUpdateStatus: Successful`
- [ ] Function URL auth = NONE + CORS เปิด และทดสอบ `curl` ได้หน้า HTML
- [ ] EventBridge rule `daily-market-close-analysis` ผูกกับฟังก์ชันเรียบร้อย
- [ ] ทดสอบกดวิเคราะห์หน้าเว็บ 1 รอบ มีข้อมูลลงตาราง DynamoDB จริง
- [ ] ลบทรัพยากรครบทั้งหมดหลังเลิกใช้ตามขั้นที่ 7
