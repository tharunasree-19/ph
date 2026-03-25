"""
AWS Phoenix Protocol - Main Application
Global E-Commerce Resilience Platform
"""

from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file
from flask_cors import CORS
import boto3
import json
import os
import uuid
import hashlib
import base64
import pandas as pd
import io
import time
from datetime import datetime, timedelta
from functools import wraps
import redis
from botocore.exceptions import ClientError

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "phoenix-protocol-secret-2024")
CORS(app)

# ─── AWS Configuration ────────────────────────────────────────────────────────
AWS_REGION        = os.environ.get("AWS_REGION", "us-west-2")
S3_BUCKET         = os.environ.get("S3_BUCKET", "phoenix-ecom-data-tharuna")
DYNAMODB_TABLE    = os.environ.get("DYNAMODB_TABLE", "phoenix-users")
SQS_QUEUE_URL     = os.environ.get("SQS_QUEUE_URL", "https://sqs.us-west-2.amazonaws.com/940482422578/phoenix-analysis-queue")
SES_SENDER        = os.environ.get("SES_SENDER", "tharuna@thesmartbridge.com")
ELASTICACHE_HOST  = os.environ.get("ELASTICACHE_HOST", "localhost")
ELASTICACHE_PORT  = int(os.environ.get("ELASTICACHE_PORT", 6379))

# ─── AWS Clients ──────────────────────────────────────────────────────────────
def get_aws_client(service):
    return boto3.client(service, region_name=AWS_REGION)

def get_aws_resource(service):
    return boto3.resource(service, region_name=AWS_REGION)

# Redis / ElastiCache
try:
    cache = redis.Redis(host=ELASTICACHE_HOST, port=ELASTICACHE_PORT, decode_responses=True)
    cache.ping()
    CACHE_ENABLED = True
except Exception:
    CACHE_ENABLED = False
    cache = None

# ─── In-Memory Demo Store (replaces DynamoDB for local dev) ───────────────────
DEMO_USERS = {
    "loader@phoenix.com": {
        "user_id": "u001",
        "name": "Data Loader",
        "email": "loader@phoenix.com",
        "password_hash": hashlib.sha256("loader123".encode()).hexdigest(),
        "role": "data_loader",
        "created_at": "2024-01-01"
    },
    "analyst@phoenix.com": {
        "user_id": "u002",
        "name": "Business Analyst",
        "email": "analyst@phoenix.com",
        "password_hash": hashlib.sha256("analyst123".encode()).hexdigest(),
        "role": "analyst",
        "created_at": "2024-01-01"
    },
    "admin@phoenix.com": {
        "user_id": "u003",
        "name": "Admin",
        "email": "admin@phoenix.com",
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
        "role": "admin",
        "created_at": "2024-01-01"
    }
}

# In-memory data store for uploaded datasets
UPLOADED_DATASETS = {}
QUERY_HISTORY     = []
ANALYSIS_CACHE    = {}

# ─── Role Permissions ─────────────────────────────────────────────────────────
ROLE_PERMISSIONS = {
    "data_loader": ["upload_data", "view_uploads", "view_dashboard"],
    "analyst":     ["view_data", "query_data", "voice_query", "view_charts",
                    "export_report", "view_dashboard"],
    "admin":       ["upload_data", "view_uploads", "view_data", "query_data",
                    "voice_query", "view_charts", "export_report",
                    "manage_users", "view_audit", "view_dashboard",
                    "delete_data", "send_report"]
}

# ─── Auth Decorators ──────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized", "redirect": "/login"}), 401
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"error": "Unauthorized"}), 401
            if session.get("role") not in roles:
                return jsonify({"error": "Forbidden - insufficient permissions"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"error": "Unauthorized"}), 401
            user_role = session.get("role", "")
            if permission not in ROLE_PERMISSIONS.get(user_role, []):
                return jsonify({"error": f"Permission '{permission}' required"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ─── Helper Functions ─────────────────────────────────────────────────────────
def log_audit(user_id, action, details=""):
    entry = {
        "audit_id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": action,
        "details": details,
        "timestamp": datetime.utcnow().isoformat(),
        "ip": request.remote_addr
    }
    QUERY_HISTORY.append(entry)
    return entry

def get_dataset(dataset_id):
    if dataset_id in ANALYSIS_CACHE:
        data = ANALYSIS_CACHE[dataset_id]
        if isinstance(data, str):
            return pd.read_json(data)
        return data
    return None

def analyze_dataframe(df, question):
    """Core NLP-style analysis of a DataFrame based on a natural language question."""
    question_lower = question.lower()
    result = {"type": "text", "answer": "", "chart_data": None, "chart_type": None}

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    text_cols    = df.select_dtypes(include="object").columns.tolist()
    all_cols     = df.columns.tolist()

    # ── Revenue / Sales ───────────────────────────────────────────────────────
    if any(w in question_lower for w in ["revenue", "sales", "total", "sum"]):
        col = next((c for c in numeric_cols if any(k in c.lower()
                    for k in ["revenue", "sales", "amount", "price", "total"])), None)
        if col:
            total = df[col].sum()
            avg   = df[col].mean()
            mx    = df[col].max()
            mn    = df[col].min()
            result["answer"] = (
                f"📊 **{col} Analysis**\n"
                f"• Total: ₹{total:,.2f}\n"
                f"• Average: ₹{avg:,.2f}\n"
                f"• Highest: ₹{mx:,.2f}\n"
                f"• Lowest: ₹{mn:,.2f}"
            )
            # Chart: group by first text col
            group_col = text_cols[0] if text_cols else None
            if group_col:
                grouped = df.groupby(group_col)[col].sum().reset_index()
                result["chart_data"] = {
                    "labels": grouped[group_col].tolist(),
                    "datasets": [{"label": f"Total {col}", "data": grouped[col].tolist()}]
                }
                result["chart_type"] = "bar"
        else:
            result["answer"] = "No revenue/sales column found in the dataset."

    # ── Top / Best Performers ─────────────────────────────────────────────────
    elif any(w in question_lower for w in ["top", "best", "highest", "leading"]):
        n   = 5
        col = next((c for c in numeric_cols), None)
        grp = next((c for c in text_cols), None)
        if col and grp:
            top = df.groupby(grp)[col].sum().nlargest(n).reset_index()
            rows = "\n".join([f"  {i+1}. {row[grp]}: {row[col]:,.2f}"
                              for i, row in top.iterrows()])
            result["answer"] = f"🏆 **Top {n} by {col}:**\n{rows}"
            result["chart_data"] = {
                "labels": top[grp].tolist(),
                "datasets": [{"label": col, "data": top[col].tolist()}]
            }
            result["chart_type"] = "bar"
        else:
            result["answer"] = "Could not determine top performers - check your data columns."

    # ── Trend / Monthly ───────────────────────────────────────────────────────
    elif any(w in question_lower for w in ["trend", "month", "over time", "growth"]):
        date_col = next((c for c in all_cols if any(k in c.lower()
                         for k in ["date", "month", "year", "time", "period"])), None)
        val_col  = next((c for c in numeric_cols), None)
        if date_col and val_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df_valid = df.dropna(subset=[date_col])
            trend = df_valid.groupby(df_valid[date_col].dt.to_period("M"))[val_col].sum()
            result["answer"] = (
                f"📈 **Monthly Trend for {val_col}**\n"
                f"• Periods: {len(trend)}\n"
                f"• Peak: {trend.idxmax()} (₹{trend.max():,.2f})\n"
                f"• Lowest: {trend.idxmin()} (₹{trend.min():,.2f})"
            )
            result["chart_data"] = {
                "labels": [str(p) for p in trend.index],
                "datasets": [{"label": val_col, "data": trend.tolist()}]
            }
            result["chart_type"] = "line"
        else:
            result["answer"] = "No date/time column found for trend analysis."

    # ── Count / Distribution ───────────────────────────────────────────────────
    elif any(w in question_lower for w in ["count", "how many", "distribution", "breakdown"]):
        grp = next((c for c in text_cols), None)
        if grp:
            counts = df[grp].value_counts().reset_index()
            counts.columns = [grp, "count"]
            result["answer"] = (
                f"📋 **Distribution by {grp}**\n"
                + "\n".join([f"  • {row[grp]}: {row['count']}"
                              for _, row in counts.head(8).iterrows()])
            )
            result["chart_data"] = {
                "labels": counts[grp].head(8).tolist(),
                "datasets": [{"label": "Count", "data": counts["count"].head(8).tolist()}]
            }
            result["chart_type"] = "pie"
        else:
            result["answer"] = f"Dataset has {len(df)} rows and {len(all_cols)} columns."

    # ── Average ────────────────────────────────────────────────────────────────
    elif any(w in question_lower for w in ["average", "mean", "avg"]):
        if numeric_cols:
            avgs = df[numeric_cols].mean()
            lines = "\n".join([f"  • {c}: {v:,.2f}" for c, v in avgs.items()])
            result["answer"] = f"📊 **Average Values:**\n{lines}"
            result["chart_data"] = {
                "labels": numeric_cols,
                "datasets": [{"label": "Average", "data": avgs.tolist()}]
            }
            result["chart_type"] = "bar"
        else:
            result["answer"] = "No numeric columns found."

    # ── Summary / Overview ─────────────────────────────────────────────────────
    else:
        result["answer"] = (
            f"📋 **Dataset Summary**\n"
            f"• Rows: {len(df):,}\n"
            f"• Columns: {len(all_cols)}\n"
            f"• Numeric columns: {', '.join(numeric_cols) or 'None'}\n"
            f"• Text columns: {', '.join(text_cols) or 'None'}\n"
            f"• Missing values: {df.isnull().sum().sum():,}"
        )
        if numeric_cols:
            vals = df[numeric_cols[0]]
            result["chart_data"] = {
                "labels": [str(i) for i in range(min(20, len(df)))],
                "datasets": [{"label": numeric_cols[0], "data": vals.head(20).tolist()}]
            }
            result["chart_type"] = "line"

    return result

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    if role == "data_loader":
        return render_template("loader_dashboard.html", user=session)
    elif role == "analyst":
        return render_template("analyst_dashboard.html", user=session)
    elif role == "admin":
        return render_template("admin_dashboard.html", user=session)
    return redirect(url_for("login_page"))

# ─── Auth API ─────────────────────────────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data  = request.json or {}
    email = data.get("email", "").strip().lower()
    pwd   = data.get("password", "")

    user = DEMO_USERS.get(email)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
    if pwd_hash != user["password_hash"]:
        return jsonify({"error": "Invalid credentials"}), 401

    session["user_id"]   = user["user_id"]
    session["email"]     = user["email"]
    session["name"]      = user["name"]
    session["role"]      = user["role"]
    session["logged_in"] = True

    log_audit(user["user_id"], "LOGIN", f"User {email} logged in")

    return jsonify({
        "success": True,
        "user": {
            "user_id":     user["user_id"],
            "name":        user["name"],
            "email":       user["email"],
            "role":        user["role"],
            "permissions": ROLE_PERMISSIONS.get(user["role"], [])
        },
        "redirect": "/dashboard"
    })

@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    if "user_id" in session:
        log_audit(session["user_id"], "LOGOUT")
    session.clear()
    return jsonify({"success": True, "redirect": "/login"})

@app.route("/api/auth/me")
@login_required
def api_me():
    return jsonify({
        "user_id":     session.get("user_id"),
        "name":        session.get("name"),
        "email":       session.get("email"),
        "role":        session.get("role"),
        "permissions": ROLE_PERMISSIONS.get(session.get("role", ""), [])
    })

# ─── Data Upload API ──────────────────────────────────────────────────────────

@app.route("/api/data/upload", methods=["POST"])
@login_required
@permission_required("upload_data")
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename.endswith((".xlsx", ".xls", ".csv")):
        return jsonify({"error": "Only Excel (.xlsx, .xls) and CSV files allowed"}), 400

    dataset_id   = str(uuid.uuid4())[:8]
    dataset_name = request.form.get("dataset_name", f.filename)

    try:
        if f.filename.endswith(".csv"):
            df = pd.read_csv(f)
        else:
            df = pd.read_excel(f)

        # Store in memory
        ANALYSIS_CACHE[dataset_id] = df.to_json()
        UPLOADED_DATASETS[dataset_id] = {
            "dataset_id":   dataset_id,
            "name":         dataset_name,
            "filename":     f.filename,
            "rows":         len(df),
            "columns":      list(df.columns),
            "col_count":    len(df.columns),
            "uploaded_by":  session["user_id"],
            "uploaded_at":  datetime.utcnow().isoformat(),
            "size_kb":      round(df.memory_usage(deep=True).sum() / 1024, 2)
        }

        log_audit(session["user_id"], "UPLOAD", f"Dataset '{dataset_name}' ({len(df)} rows)")

        # Simulate S3 upload notification
        try:
            s3 = get_aws_client("s3")
            # s3.put_object(Bucket=S3_BUCKET, Key=f"datasets/{dataset_id}.json", Body=df.to_json())
        except Exception:
            pass  # Demo mode - S3 not required locally

        return jsonify({
            "success":    True,
            "dataset_id": dataset_id,
            "name":       dataset_name,
            "rows":       len(df),
            "columns":    list(df.columns),
            "preview":    df.head(5).to_dict(orient="records")
        })

    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500

@app.route("/api/data/datasets")
@login_required
def api_list_datasets():
    datasets = list(UPLOADED_DATASETS.values())
    return jsonify({"datasets": datasets})

@app.route("/api/data/preview/<dataset_id>")
@login_required
def api_preview(dataset_id):
    df = get_dataset(dataset_id)
    if df is None:
        return jsonify({"error": "Dataset not found"}), 404
    return jsonify({
        "columns": list(df.columns),
        "rows":    len(df),
        "preview": df.head(10).to_dict(orient="records"),
        "dtypes":  {c: str(t) for c, t in df.dtypes.items()}
    })

@app.route("/api/data/delete/<dataset_id>", methods=["DELETE"])
@login_required
@permission_required("delete_data")
def api_delete_dataset(dataset_id):
    if dataset_id in UPLOADED_DATASETS:
        del UPLOADED_DATASETS[dataset_id]
    if dataset_id in ANALYSIS_CACHE:
        del ANALYSIS_CACHE[dataset_id]
    log_audit(session["user_id"], "DELETE_DATASET", dataset_id)
    return jsonify({"success": True})

# ─── Query / Analysis API ─────────────────────────────────────────────────────

@app.route("/api/query/text", methods=["POST"])
@login_required
@permission_required("query_data")
def api_query_text():
    data       = request.json or {}
    question   = data.get("question", "").strip()
    dataset_id = data.get("dataset_id", "")

    if not question:
        return jsonify({"error": "Question is required"}), 400

    df = get_dataset(dataset_id)
    if df is None:
        if UPLOADED_DATASETS:
            dataset_id = list(UPLOADED_DATASETS.keys())[-1]
            df = get_dataset(dataset_id)
        if df is None:
            return jsonify({"error": "No dataset available. Please upload data first."}), 404

    # Check cache
    cache_key = f"{dataset_id}:{hashlib.md5(question.encode()).hexdigest()}"
    if CACHE_ENABLED:
        cached = cache.get(cache_key)
        if cached:
            return jsonify(json.loads(cached))

    result = analyze_dataframe(df, question)

    response = {
        "success":    True,
        "question":   question,
        "answer":     result["answer"],
        "chart_data": result.get("chart_data"),
        "chart_type": result.get("chart_type"),
        "dataset_id": dataset_id,
        "timestamp":  datetime.utcnow().isoformat()
    }

    if CACHE_ENABLED:
        cache.setex(cache_key, 300, json.dumps(response))

    log_audit(session["user_id"], "QUERY", question)
    QUERY_HISTORY.append({
        "type": "query", "question": question,
        "user_id": session["user_id"], "dataset_id": dataset_id,
        "timestamp": datetime.utcnow().isoformat()
    })

    return jsonify(response)

# ─── Voice API (Polly + Browser SpeechRecognition) ────────────────────────────

@app.route("/api/voice/synthesize", methods=["POST"])
@login_required
def api_voice_synthesize():
    """Convert text to speech using Amazon Polly."""
    data = request.json or {}
    text = data.get("text", "")[:500]

    if not text:
        return jsonify({"error": "Text required"}), 400

    try:
        polly = get_aws_client("polly")
        resp  = polly.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural"
        )
        audio_data = resp["AudioStream"].read()
        audio_b64  = base64.b64encode(audio_data).decode("utf-8")
        return jsonify({"success": True, "audio_base64": audio_b64, "format": "mp3"})
    except Exception as e:
        return jsonify({"error": f"Polly unavailable: {str(e)}", "fallback": "browser_tts"})

@app.route("/api/voice/query", methods=["POST"])
@login_required
@permission_required("voice_query")
def api_voice_query():
    """Process a voice-transcribed question."""
    data       = request.json or {}
    transcript = data.get("transcript", "").strip()
    dataset_id = data.get("dataset_id", "")

    if not transcript:
        return jsonify({"error": "No transcript received"}), 400

    df = get_dataset(dataset_id)
    if df is None and UPLOADED_DATASETS:
        dataset_id = list(UPLOADED_DATASETS.keys())[-1]
        df = get_dataset(dataset_id)

    if df is None:
        return jsonify({
            "success":  False,
            "answer":   "No dataset loaded. Please ask the Data Loader to upload data first.",
            "question": transcript
        })

    result = analyze_dataframe(df, transcript)
    log_audit(session["user_id"], "VOICE_QUERY", transcript)

    return jsonify({
        "success":    True,
        "question":   transcript,
        "answer":     result["answer"],
        "chart_data": result.get("chart_data"),
        "chart_type": result.get("chart_type"),
        "dataset_id": dataset_id,
        "source":     "voice",
        "timestamp":  datetime.utcnow().isoformat()
    })

# ─── Reports API ──────────────────────────────────────────────────────────────

@app.route("/api/reports/summary/<dataset_id>")
@login_required
@permission_required("export_report")
def api_summary_report(dataset_id):
    df = get_dataset(dataset_id)
    if df is None:
        return jsonify({"error": "Dataset not found"}), 404

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    text_cols    = df.select_dtypes(include="object").columns.tolist()

    report = {
        "dataset_id":     dataset_id,
        "generated_at":   datetime.utcnow().isoformat(),
        "generated_by":   session.get("name"),
        "total_rows":     len(df),
        "total_columns":  len(df.columns),
        "numeric_summary": {},
        "text_summary":    {},
        "missing_values":  df.isnull().sum().to_dict()
    }

    for col in numeric_cols[:5]:
        report["numeric_summary"][col] = {
            "sum":    round(df[col].sum(), 2),
            "mean":   round(df[col].mean(), 2),
            "min":    round(df[col].min(), 2),
            "max":    round(df[col].max(), 2),
            "std":    round(df[col].std(), 2)
        }

    for col in text_cols[:3]:
        vc = df[col].value_counts()
        report["text_summary"][col] = {
            "unique_values": int(df[col].nunique()),
            "top_value":     str(vc.index[0]) if len(vc) > 0 else "N/A",
            "top_count":     int(vc.iloc[0]) if len(vc) > 0 else 0
        }

    log_audit(session["user_id"], "EXPORT_REPORT", dataset_id)
    report["missing_values"] = {k: int(v) for k, v in report["missing_values"].items()}
    return jsonify(make_json_safe(report))

@app.route("/api/reports/export/<dataset_id>")
@login_required
@permission_required("export_report")
def api_export_csv(dataset_id):
    df = get_dataset(dataset_id)
    if df is None:
        return jsonify({"error": "Dataset not found"}), 404

    output = io.BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)

    log_audit(session["user_id"], "EXPORT_CSV", dataset_id)
    return send_file(
        output,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"phoenix_export_{dataset_id}.csv"
    )

@app.route("/api/reports/send-email", methods=["POST"])
@login_required
@permission_required("send_report")
def api_send_email():
    data       = request.json or {}
    recipient  = data.get("email", "")
    dataset_id = data.get("dataset_id", "")
    subject    = data.get("subject", "Phoenix Protocol - Report")

    if not recipient:
        return jsonify({"error": "Email required"}), 400

    try:
        ses = get_aws_client("ses")
        df  = get_dataset(dataset_id)
        body = f"Report generated at {datetime.utcnow().isoformat()} by {session.get('name')}"
        if df is not None:
            body += f"\n\nDataset: {dataset_id}\nRows: {len(df)}\nColumns: {', '.join(df.columns)}"

        ses.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject},
                "Body":    {"Text": {"Data": body}}
            }
        )
        log_audit(session["user_id"], "SEND_EMAIL", recipient)
        return jsonify({"success": True, "message": f"Report sent to {recipient}"})
    except Exception as e:
        return jsonify({"error": f"Email send failed: {str(e)}"}), 500

# ─── Admin API ────────────────────────────────────────────────────────────────

@app.route("/api/admin/users")
@login_required
@permission_required("manage_users")
def api_list_users():
    users = [{k: v for k, v in u.items() if k != "password_hash"}
             for u in DEMO_USERS.values()]
    return jsonify({"users": users})

@app.route("/api/admin/audit")
@login_required
@permission_required("view_audit")
def api_audit_log():
    logs = [e for e in QUERY_HISTORY if "action" in e]
    return jsonify({"audit_log": logs[-50:]})

@app.route("/api/admin/stats")
@login_required
@permission_required("manage_users")
def api_admin_stats():
    return jsonify({
        "total_datasets":  len(UPLOADED_DATASETS),
        "total_queries":   len([e for e in QUERY_HISTORY if e.get("type") == "query"]),
        "total_users":     len(DEMO_USERS),
        "cache_enabled":   CACHE_ENABLED,
        "datasets":        list(UPLOADED_DATASETS.values()),
        "recent_activity": QUERY_HISTORY[-10:]
    })

# ─── Health Check ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def api_health():
    return jsonify({
        "status":         "healthy",
        "service":        "AWS Phoenix Protocol",
        "version":        "1.0.0",
        "region":         AWS_REGION,
        "cache_enabled":  CACHE_ENABLED,
        "datasets_loaded": len(UPLOADED_DATASETS),
        "timestamp":      datetime.utcnow().isoformat()
    })

# ─── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
