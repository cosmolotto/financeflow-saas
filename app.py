"""
FinanceFlow SaaS — Complete Flask App
Matches worker.py SQLite schema. All routes wired.
"""

from flask import Flask, request, jsonify, render_template, redirect, session
import sqlite3, os, json, hashlib, secrets, urllib.parse, urllib.request, time
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-railway")

DB            = "financeflow.db"
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
APP_URL       = os.environ.get("APP_URL", "https://web-production-0272d.up.railway.app")
REDIRECT_URI  = f"{APP_URL}/api/channels/callback"
BREVO_KEY     = os.environ.get("BREVO_API_KEY", "")
MASTER_KEY    = os.environ.get("MASTER_ADMIN_KEY", "MASTER_ADMIN_KEY")

PLANS = {
    "starter": {"channels": 1,  "videos_per_week": 3,   "price": 0},
    "pro":     {"channels": 3,  "videos_per_week": 14,  "price": 29},
    "agency":  {"channels": 10, "videos_per_week": 999, "price": 99},
}

def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT NOT NULL,
            full_name      TEXT,
            plan           TEXT DEFAULT 'starter',
            is_admin       INTEGER DEFAULT 0,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reset_token    TEXT,
            reset_expires  INTEGER
        );
        CREATE TABLE IF NOT EXISTS channels (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER,
            channel_name        TEXT,
            youtube_channel_id  TEXT,
            refresh_token       TEXT,
            access_token        TEXT,
            niche               TEXT DEFAULT 'personal_finance',
            video_type          TEXT DEFAULT 'short',
            schedule            TEXT DEFAULT 'daily',
            active              INTEGER DEFAULT 1,
            videos_uploaded     INTEGER DEFAULT 0,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS queue (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER,
            channel_id     INTEGER,
            video_type     TEXT DEFAULT 'short',
            niche          TEXT DEFAULT 'personal_finance',
            custom_prompt  TEXT,
            custom_title   TEXT,
            status         TEXT DEFAULT 'pending',
            progress       TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS videos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            channel_id   INTEGER,
            title        TEXT,
            type         TEXT,
            status       TEXT,
            youtube_id   TEXT,
            youtube_url  TEXT,
            script       TEXT,
            error_msg    TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS social_accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id  INTEGER,
            platform    TEXT,
            credentials TEXT,
            active      INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS social_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id    INTEGER,
            channel_id  INTEGER,
            platform    TEXT,
            post_url    TEXT,
            status      TEXT,
            error_msg   TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def make_token(user_id, is_admin=False):
    import base64
    payload = json.dumps({"user_id": user_id, "is_admin": is_admin, "ts": int(time.time())})
    return base64.urlsafe_b64encode(payload.encode()).decode()

def parse_token(token):
    try:
        import base64
        return json.loads(base64.urlsafe_b64decode(token + "==").decode())
    except:
        return None

def get_current_user():
    token = (request.headers.get("Authorization", "").replace("Bearer ", "")
             or session.get("token", ""))
    return parse_token(token)

def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        user = get_current_user()
        if not user:
            return (jsonify({"error": "Unauthorized"}), 401) if request.is_json else redirect("/")
        request.uid = user["user_id"]
        request.is_admin = user.get("is_admin", False)
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        user = get_current_user()
        if not user or not user.get("is_admin"):
            return jsonify({"error": "Admin only"}), 403
        request.uid = user["user_id"]
        return f(*a, **kw)
    return wrap

def send_email(to_email, to_name, subject, html):
    if not BREVO_KEY:
        print(f"[EMAIL] BREVO_API_KEY not set — skipping email to {to_email}")
        return False
    try:
        payload = json.dumps({
            "sender":      {"name": "FinanceFlow", "email": "noreply@financeflow.app"},
            "to":          [{"email": to_email, "name": to_name or to_email}],
            "subject":     subject,
            "htmlContent": html
        }).encode()
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "accept":       "application/json",
                "api-key":      BREVO_KEY,
                "content-type": "application/json"
            }
        )
        with urllib.request.urlopen(req) as r:
            return r.status in (200, 201)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/dashboard")
def dashboard():
    if not get_current_user():
        return redirect("/")
    return render_template("dashboard.html")

@app.route("/admin")
def admin_page():
    user = get_current_user()
    if not user or not user.get("is_admin"):
        return redirect("/")
    return render_template("admin.html")

@app.route("/api/auth/register", methods=["POST"])
def register():
    d = request.get_json() or {}
    email     = d.get("email", "").strip().lower()
    password  = d.get("password", "")
    full_name = d.get("full_name", "")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO users (email, password_hash, full_name) VALUES (?,?,?)",
                   (email, hash_pw(password), full_name))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        token = make_token(user["id"])
        session["token"] = token
        send_email(email, full_name, "Welcome to FinanceFlow! 🚀", f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Welcome to FinanceFlow, {full_name or 'Creator'}!</h2>
            <p>Your account is ready. Connect your YouTube channel and we'll handle everything.</p>
            <a href="{APP_URL}/dashboard" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;margin:16px 0">
                Go to Dashboard →
            </a>
            </div>""")
        return jsonify({"token": token, "redirect": "/dashboard"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 400
    finally:
        db.close()

@app.route("/api/auth/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    email    = d.get("email", "").strip().lower()
    password = d.get("password", "")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=? AND password_hash=?",
                      (email, hash_pw(password))).fetchone()
    db.close()
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    token = make_token(user["id"], bool(user["is_admin"]))
    session["token"] = token
    return jsonify({"token": token, "redirect": "/admin" if user["is_admin"] else "/dashboard"})

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if user:
        token   = secrets.token_urlsafe(32)
        expires = int(time.time()) + 3600
        db.execute("UPDATE users SET reset_token=?, reset_expires=? WHERE email=?",
                   (token, expires, email))
        db.commit()
        link = f"{APP_URL}/reset-password?token={token}"
        send_email(email, user["full_name"], "Reset your FinanceFlow password", f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Password Reset</h2>
            <p>Click below to reset your password. Expires in 1 hour.</p>
            <a href="{link}" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;margin:16px 0">
                Reset Password →
            </a>
            </div>""")
    db.close()
    return jsonify({"status": "If that email exists, a reset link has been sent"})

@app.route("/api/auth/reset-password", methods=["POST"])
def do_reset_password():
    d = request.get_json() or {}
    token    = d.get("token", "")
    new_pass = d.get("password", "")
    if not new_pass or len(new_pass) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE reset_token=? AND reset_expires>?",
                      (token, int(time.time()))).fetchone()
    if not user:
        db.close()
        return jsonify({"error": "Invalid or expired reset link"}), 400
    db.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_expires=NULL WHERE id=?",
               (hash_pw(new_pass), user["id"]))
    db.commit()
    db.close()
    return jsonify({"status": "Password updated successfully"})

@app.route("/api/auth/me")
@login_required
def me():
    db = get_db()
    user = db.execute("SELECT id, email, full_name, plan, created_at FROM users WHERE id=?",
                      (request.uid,)).fetchone()
    db.close()
    return jsonify(dict(user)) if user else (jsonify({"error": "Not found"}), 404)

@app.route("/api/channels/connect")
@login_required
def channel_connect():
    state = f"{request.uid}:{secrets.token_hex(16)}"
    session["oauth_state"] = state
    params = urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         ("https://www.googleapis.com/auth/youtube.upload "
                          "https://www.googleapis.com/auth/youtube.readonly"),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    })
    return redirect(f"https://accounts.google.com/o/oauth2/auth?{params}")

@app.route("/api/channels/callback")
def channel_callback():
    code  = request.args.get("code", "")
    state = request.args.get("state", "")
    error = request.args.get("error", "")
    if error:
        return redirect(f"/dashboard?error={urllib.parse.quote(error)}")
    if not code:
        return redirect("/dashboard?error=no_code")
    try:
        user_id = int(state.split(":")[0])
    except:
        return redirect("/dashboard?error=invalid_state")
    try:
        data = urllib.parse.urlencode({
            "code":          code,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req) as r:
            tokens = json.loads(r.read())
    except Exception as e:
        print(f"[OAUTH] Token exchange failed: {e}")
        return redirect("/dashboard?error=token_exchange_failed")
    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    channel_name  = "My Channel"
    yt_channel_id = ""
    try:
        yt_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        with urllib.request.urlopen(yt_req) as r:
            yt_data = json.loads(r.read())
        item = yt_data["items"][0]
        channel_name  = item["snippet"]["title"]
        yt_channel_id = item["id"]
    except Exception as e:
        print(f"[OAUTH] YouTube channel fetch failed: {e}")
    db = get_db()
    existing = db.execute("SELECT id FROM channels WHERE youtube_channel_id=? AND user_id=?",
                          (yt_channel_id, user_id)).fetchone()
    if existing:
        db.execute("UPDATE channels SET refresh_token=?, access_token=?, active=1 WHERE id=?",
                   (refresh_token, access_token, existing["id"]))
    else:
        db.execute(
            "INSERT INTO channels (user_id, channel_name, youtube_channel_id, refresh_token, access_token) VALUES (?,?,?,?,?)",
            (user_id, channel_name, yt_channel_id, refresh_token, access_token)
        )
    db.commit()
    token = make_token(user_id)
    session["token"] = token
    db.close()
    return redirect("/dashboard?connected=1")

@app.route("/api/channels")
@login_required
def get_channels():
    db = get_db()
    rows = db.execute(
        "SELECT id, channel_name, youtube_channel_id, niche, video_type, schedule, videos_uploaded, created_at "
        "FROM channels WHERE user_id=? AND active=1 ORDER BY created_at DESC", (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/channels/<int:cid>", methods=["PUT"])
@login_required
def update_channel(cid):
    d = request.get_json() or {}
    db = get_db()
    db.execute("UPDATE channels SET niche=?, video_type=?, schedule=? WHERE id=? AND user_id=?",
               (d.get("niche"), d.get("video_type"), d.get("schedule"), cid, request.uid))
    db.commit(); db.close()
    return jsonify({"status": "updated"})

@app.route("/api/channels/<int:cid>", methods=["DELETE"])
@login_required
def delete_channel(cid):
    db = get_db()
    db.execute("UPDATE channels SET active=0 WHERE id=? AND user_id=?", (cid, request.uid))
    db.commit(); db.close()
    return jsonify({"status": "deleted"})

@app.route("/api/videos/generate", methods=["POST"])
@login_required
def generate_video():
    d = request.get_json() or {}
    channel_id    = d.get("channel_id")
    niche         = d.get("niche", "personal_finance")
    video_type    = d.get("video_type", "short")
    custom_prompt = d.get("custom_prompt", "")
    custom_title  = d.get("custom_title", "")
    db = get_db()
    ch = db.execute("SELECT id FROM channels WHERE id=? AND user_id=?",
                    (channel_id, request.uid)).fetchone()
    if not ch:
        db.close()
        return jsonify({"error": "Channel not found"}), 404
    job_id = db.execute(
        "INSERT INTO queue (user_id, channel_id, video_type, niche, custom_prompt, custom_title) VALUES (?,?,?,?,?,?)",
        (request.uid, channel_id, video_type, niche, custom_prompt, custom_title)
    ).lastrowid
    db.commit(); db.close()
    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/api/videos/queue")
@login_required
def get_queue():
    db = get_db()
    rows = db.execute(
        "SELECT q.*, c.channel_name FROM queue q LEFT JOIN channels c ON q.channel_id=c.id "
        "WHERE q.user_id=? ORDER BY q.created_at DESC LIMIT 30", (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/videos/status/<int:job_id>")
@login_required
def job_status(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM queue WHERE id=? AND user_id=?",
                     (job_id, request.uid)).fetchone()
    db.close()
    return jsonify(dict(job)) if job else (jsonify({"error": "Not found"}), 404)

@app.route("/api/videos")
@login_required
def get_videos():
    db = get_db()
    rows = db.execute(
        "SELECT v.*, c.channel_name FROM videos v LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50", (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/social/<int:cid>")
@login_required
def get_social(cid):
    db = get_db()
    rows = db.execute("SELECT id, platform, active FROM social_accounts WHERE channel_id=?",
                      (cid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/social/<int:cid>", methods=["POST"])
@login_required
def save_social(cid):
    d = request.get_json() or {}
    platform    = d.get("platform")
    credentials = json.dumps(d.get("credentials", {}))
    db = get_db()
    ex = db.execute("SELECT id FROM social_accounts WHERE channel_id=? AND platform=?",
                    (cid, platform)).fetchone()
    if ex:
        db.execute("UPDATE social_accounts SET credentials=?, active=1 WHERE id=?",
                   (credentials, ex["id"]))
    else:
        db.execute("INSERT INTO social_accounts (channel_id, platform, credentials) VALUES (?,?,?)",
                   (cid, platform, credentials))
    db.commit(); db.close()
    return jsonify({"status": "saved"})

@app.route("/api/stats")
@login_required
def stats():
    db = get_db()
    channels   = db.execute("SELECT COUNT(*) FROM channels WHERE user_id=? AND active=1", (request.uid,)).fetchone()[0]
    uploaded   = db.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND status='uploaded'", (request.uid,)).fetchone()[0]
    pending    = db.execute("SELECT COUNT(*) FROM queue WHERE user_id=? AND status='pending'", (request.uid,)).fetchone()[0]
    processing = db.execute("SELECT COUNT(*) FROM queue WHERE user_id=? AND status='processing'", (request.uid,)).fetchone()[0]
    user       = db.execute("SELECT plan FROM users WHERE id=?", (request.uid,)).fetchone()
    db.close()
    plan = user["plan"] if user else "starter"
    return jsonify({
        "channels": channels, "videos_uploaded": uploaded,
        "queue_pending": pending, "queue_processing": processing,
        "plan": plan, "plan_limits": PLANS.get(plan, PLANS["starter"]),
    })

@app.route("/api/admin/create", methods=["POST"])
def create_admin():
    d = request.get_json() or {}
    if d.get("master_key") != MASTER_KEY:
        return jsonify({"error": "Not authorized"}), 403
    email    = d.get("email", "").strip().lower()
    password = d.get("password", "")
    db = get_db()
    try:
        db.execute("INSERT INTO users (email, password_hash, is_admin) VALUES (?,?,1)",
                   (email, hash_pw(password)))
    except sqlite3.IntegrityError:
        db.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
    db.commit(); db.close()
    return jsonify({"status": "admin created"})

@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_vids  = db.execute("SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0]
    total_chans = db.execute("SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    pro         = db.execute("SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0]
    agency      = db.execute("SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0]
    db.close()
    return jsonify({
        "total_users": total_users, "total_videos": total_vids,
        "total_channels": total_chans, "mrr": (pro * 29) + (agency * 99),
        "pro_users": pro, "agency_users": agency,
    })

@app.route("/api/admin/users")
@admin_required
def admin_users():
    db = get_db()
    rows = db.execute(
        "SELECT id, email, full_name, plan, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/users/<int:uid>/plan", methods=["PUT"])
@admin_required
def admin_set_plan(uid):
    d = request.get_json() or {}
    db = get_db()
    db.execute("UPDATE users SET plan=? WHERE id=?", (d.get("plan", "starter"), uid))
    db.commit(); db.close()
    return jsonify({"status": "updated"})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit(); db.close()
    return jsonify({"status": "deleted"})

@app.route("/api/admin/channels")
@admin_required
def admin_channels():
    db = get_db()
    rows = db.execute(
        "SELECT c.*, u.email FROM channels c LEFT JOIN users u ON c.user_id=u.id WHERE c.active=1 ORDER BY c.created_at DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/videos")
@admin_required
def admin_videos():
    db = get_db()
    rows = db.execute(
        "SELECT v.*, u.email, c.channel_name FROM videos v "
        "LEFT JOIN users u ON v.user_id=u.id "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "ORDER BY v.created_at DESC LIMIT 100"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "FinanceFlow SaaS"})

init_db()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
