# 🔥 AWS Phoenix Protocol
## Endgame Resilience for Global E-Commerce

---

## Project Structure

```
aws-phoenix-protocol/
│
├── app.py                          # Main Flask backend (all APIs)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
│
├── templates/                      # HTML pages (Jinja2)
│   ├── login.html                  # Login page (all 3 roles)
│   ├── loader_dashboard.html       # Data Loader dashboard
│   ├── analyst_dashboard.html      # Analyst dashboard (voice + charts)
│   └── admin_dashboard.html        # Admin dashboard (full control)
│
├── static/
│   └── css/
│       └── dashboard.css           # Shared dashboard styles
│
├── uploads/                        # Temp upload storage
└── exports/                        # Generated reports
```

---

## AWS Services Used

| Service | Role |
|---|---|
| Amazon EC2 (Auto Scaling) | Compute — runs Flask app, scales on demand |
| Amazon S3 | Stores uploaded Excel/CSV datasets |
| AWS Lambda | Triggered on S3 upload for processing |
| Amazon DynamoDB | User sessions, query history, audit logs |
| Amazon ElastiCache (Redis) | Caches analysis results |
| Amazon RDS (Multi-AZ) | Relational DB for structured data |
| Amazon Route 53 | DNS + active/passive failover |
| AWS Application LB | Distributes traffic across EC2 instances |
| Amazon CloudFront | Global CDN for static assets |
| Amazon SQS | Async job queue for heavy analysis |
| Amazon EventBridge | Schedules reports and triggers |
| Amazon Polly | Converts analysis answers to speech |
| Amazon SES | Sends email reports |
| AWS WAF | Threat protection |
| AWS IAM | Role-based access control |
| Amazon VPC | Isolated network environment |

---

## User Roles

### 📤 Data Loader
- **Login:** loader@phoenix.com / loader123
- Upload Excel (.xlsx) or CSV files → stored in S3
- View upload history and dataset previews
- Pipeline visualization: Browser → EC2 → S3 → Lambda → DynamoDB → SQS

### 📈 Analyst
- **Login:** analyst@phoenix.com / analyst123
- Voice query using microphone (browser SpeechRecognition + Amazon Polly response)
- Text query with natural language understanding
- Auto-generated charts (bar, line, pie, doughnut)
- Export CSV reports
- Summary reports with statistics

### 👑 Admin
- **Login:** admin@phoenix.com / admin123
- Everything above PLUS:
- User management + IAM role overview
- Full audit log (all user actions)
- Delete datasets
- Send email reports via Amazon SES
- AWS architecture diagram view
- Full system status

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your AWS credentials

# 3. Run locally
python app.py

# 4. Open browser
# http://localhost:5000

# 5. Login with demo credentials
# loader@phoenix.com  / loader123
# analyst@phoenix.com / analyst123
# admin@phoenix.com   / admin123
```

---

## Voice Query Flow

```
User speaks → Browser Web Speech API (transcript)
→ POST /api/voice/query → Flask backend
→ Pandas analysis of Excel dataset
→ Answer + Chart data returned
→ Amazon Polly synthesizes voice response
→ Browser plays MP3 audio
→ Chart renders with Chart.js
```

---

## Data Analysis Capabilities

Ask in natural language:
- "What is the total revenue?"
- "Show me the top 5 best performing categories"
- "What is the sales trend over time?"
- "Give me a count breakdown by region"
- "What is the average order value?"
- "Give me a complete summary"

---

## AWS Deployment

```bash
# EC2 with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# With systemd service (recommended)
# Place in /etc/systemd/system/phoenix.service

# Environment variables via AWS Systems Manager Parameter Store
# or EC2 Instance Profile + IAM Role
```

---

## Architecture: Active/Passive Multi-Region

```
Primary Region (us-east-1)
  └── ALB → EC2 Auto Scaling Group (3 instances)
        ├── ElastiCache Redis
        ├── RDS Multi-AZ (MySQL)
        └── S3 (with CRR)

Failover (us-west-2) — Passive Standby
  └── Route 53 health checks auto-redirect on failure

Global
  └── CloudFront (CDN) → WAF → Route 53
```