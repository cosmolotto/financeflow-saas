"""
FinanceFlow SaaS — Complete Flask App
Features: JWT auth, multi-provider payments, OpenAI scripts, Redis/Celery queue
"""

from flask import Flask, request, jsonify, render_template, redirect, session
import sqlite3, os, json, hashlib, secrets, urllib.parse, urllib.request, time, random
from functools import wraps

# ── Optional dependencies ─────────────────────────────────────────────────────
try:
    import jwt as pyjwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    print("[WARN] PyJWT not installed — using insecure base64 tokens. pip install PyJWT")

try:
    import stripe as stripe_lib
    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False

try:
    import openai as openai_lib
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from celery import Celery as _Celery
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False

# ── App & config ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-railway")

DB               = "financeflow.db"
CLIENT_ID        = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET    = os.environ.get("GOOGLE_CLIENT_SECRET", "")
APP_URL          = os.environ.get("APP_URL", "https://web-production-39b44.up.railway.app")
REDIRECT_URI     = f"{APP_URL}/api/channels/callback"
BREVO_KEY        = os.environ.get("BREVO_API_KEY", "")
MASTER_KEY       = os.environ.get("MASTER_ADMIN_KEY", "MASTER_ADMIN_KEY")
JWT_SECRET       = os.environ.get("SECRET_KEY", "change-me-in-railway")
JWT_ALGO         = "HS256"
STRIPE_KEY       = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WH_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
OPENAI_KEY       = os.environ.get("OPENAI_API_KEY", "")
REDIS_URL        = os.environ.get("REDIS_URL", "")

PLANS = {
    "starter": {"name": "Starter", "channels": 1,  "videos_per_week": 3,   "price": 0,  "custom_prompts": False, "social_posting": False},
    "pro":     {"name": "Pro",     "channels": 3,  "videos_per_week": 14,  "price": 29, "custom_prompts": True,  "social_posting": True},
    "agency":  {"name": "Agency",  "channels": 10, "videos_per_week": 999, "price": 99, "custom_prompts": True,  "social_posting": True},
}

# ── Stripe setup ──────────────────────────────────────────────────────────────
if HAS_STRIPE and STRIPE_KEY:
    stripe_lib.api_key = STRIPE_KEY

# ── Celery/Redis setup ────────────────────────────────────────────────────────
celery_app = None
if HAS_CELERY and REDIS_URL:
    celery_app = _Celery("financeflow", broker=REDIS_URL, backend=REDIS_URL)
    celery_app.conf.update(
        task_serializer="json", result_serializer="json", accept_content=["json"]
    )
    print(f"[CELERY] Connected to Redis: {REDIS_URL[:40]}...")
else:
    print("[QUEUE] Using SQLite queue (no REDIS_URL set)")

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            email                  TEXT UNIQUE NOT NULL,
            password_hash          TEXT NOT NULL,
            full_name              TEXT,
            plan                   TEXT DEFAULT 'starter',
            is_admin               INTEGER DEFAULT 0,
            created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reset_token            TEXT,
            reset_expires          INTEGER,
            stripe_customer_id     TEXT,
            stripe_subscription_id TEXT
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
        CREATE TABLE IF NOT EXISTS payments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            amount     REAL NOT NULL,
            plan       TEXT NOT NULL,
            provider   TEXT DEFAULT 'manual',
            status     TEXT DEFAULT 'pending',
            reference  TEXT,
            notes      TEXT,
            stripe_pi  TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()

# ── Auth helpers ──────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def make_token(user_id, is_admin=False):
    payload = {
        "user_id":  user_id,
        "is_admin": is_admin,
        "iat":      int(time.time()),
        "exp":      int(time.time()) + 86400 * 30,  # 30 days
    }
    if HAS_JWT:
        return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    import base64
    return base64.urlsafe_b64encode(
        json.dumps({"user_id": user_id, "is_admin": is_admin, "ts": int(time.time())}).encode()
    ).decode()

def parse_token(token):
    if HAS_JWT:
        try:
            return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        except Exception:
            return None
    try:
        import base64
        return json.loads(base64.urlsafe_b64decode(token + "==").decode())
    except Exception:
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
        request.uid      = user["user_id"]
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

# ── Email ─────────────────────────────────────────────────────────────────────
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
                "content-type": "application/json",
            }
        )
        with urllib.request.urlopen(req) as r:
            return r.status in (200, 201)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

# ── OpenAI / Script generation ────────────────────────────────────────────────
FALLBACK_SCRIPTS = {
    "personal_finance": [
        "5 money mistakes that are killing your savings — and how to fix them fast.",
        "How to save $1,000 in 30 days with this one simple budget hack.",
        "The debt snowball vs debt avalanche: which method actually works?",
        "Why 90% of people never build wealth — and the mindset shift that changes everything.",
    ],
    "investing": [
        "Index funds vs ETFs: what nobody tells beginners.",
        "How compound interest turns $100 a month into $1 million.",
        "Warren Buffett's 3 investing rules every beginner must know.",
        "The S&P 500 explained in 60 seconds — and why it beats most fund managers.",
    ],
    "crypto": [
        "Bitcoin halving explained in 60 seconds — what it means for your money.",
        "5 altcoins with serious upside potential — my honest analysis.",
        "How to DCA into crypto without losing your shirt in a bear market.",
    ],
    "real_estate": [
        "How to buy your first rental property with almost no money down.",
        "The BRRRR method explained — real estate investing for beginners.",
        "Why house hacking might be the smartest financial move you make this decade.",
    ],
    "tax": [
        "5 legal tax deductions most people completely miss every year.",
        "How to pay less tax this year — legally — with these simple strategies.",
        "Self-employed? These tax write-offs could save you thousands.",
    ],
}

def generate_script(prompt, niche="personal_finance", video_type="short"):
    """Generate video script — OpenAI if key set, built-in fallback otherwise."""
    if OPENAI_KEY and HAS_OPENAI:
        try:
            length_hint = (
                "60-second YouTube Short (under 150 words, punchy hook, no fluff)"
                if video_type == "short"
                else "8-minute YouTube video (800–1000 words, structured with hook, body, CTA)"
            )
            system_msg = (
                "You are a viral finance content creator. Write engaging, punchy video scripts "
                "optimized for YouTube. Include a strong hook, clear value, and a call to action. "
                "No timestamps, scene directions, or stage notes — just the spoken script."
            )
            user_msg = f"Write a {length_hint} script about: {prompt or niche.replace('_', ' ')}"
            client   = openai_lib.OpenAI(api_key=OPENAI_KEY)
            resp     = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=600 if video_type == "short" else 2000,
                temperature=0.8,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[OPENAI ERROR] {e} — falling back to built-in scripts")

    # Fallback: use prompt as-is or pick from built-in pool
    if prompt:
        return (
            f"Today we're talking about: {prompt}\n\n"
            f"This is one of the most important finance topics you'll ever learn. "
            f"Stay till the end — I'm going to share something most people get completely wrong.\n\n"
            f"Here's what you need to know..."
        )
    pool = FALLBACK_SCRIPTS.get(niche, FALLBACK_SCRIPTS["personal_finance"])
    return random.choice(pool)

# ── Celery task ───────────────────────────────────────────────────────────────
if celery_app:
    @celery_app.task(name="financeflow.process_video")
    def process_video_task(job_id):
        """Generate script and queue for upload."""
        db = get_db()
        try:
            job = db.execute("SELECT * FROM queue WHERE id=?", (job_id,)).fetchone()
            if not job:
                return {"error": "job not found"}
            db.execute("UPDATE queue SET status='processing', progress='Generating script...' WHERE id=?", (job_id,))
            db.commit()
            script = generate_script(job["custom_prompt"] or "", job["niche"], job["video_type"])
            title  = (job["custom_title"] or
                      f"{job['niche'].replace('_', ' ').title()} — {job['video_type'].upper()}")
            db.execute(
                "INSERT INTO videos (user_id, channel_id, title, type, status, script) VALUES (?,?,?,?,?,?)",
                (job["user_id"], job["channel_id"], title, job["video_type"], "scripted", script)
            )
            db.execute("UPDATE queue SET status='scripted', progress='Script ready — pending upload' WHERE id=?", (job_id,))
            db.commit()
            return {"status": "scripted", "job_id": job_id}
        except Exception as e:
            db.execute("UPDATE queue SET status='failed', progress=? WHERE id=?", (str(e), job_id))
            db.commit()
            return {"error": str(e)}
        finally:
            db.close()
else:
    def process_video_task(job_id):
        pass  # SQLite worker.py handles it

# ── Page routes ───────────────────────────────────────────────────────────────
@app.route("/")
def landing():
    return render_template("landing.html", plans=PLANS)

@app.route("/dashboard")
def dashboard():
    user = get_current_user()
    if not user:
        return redirect("/")
    db = get_db()
    u  = db.execute("SELECT id, email, full_name, plan, is_admin FROM users WHERE id=?",
                    (user["user_id"],)).fetchone()
    if not u:
        db.close()
        return redirect("/")

    is_admin  = bool(u["is_admin"])
    plan_key  = u["plan"] or "starter"
    plan_data = dict(PLANS.get(plan_key, PLANS["starter"]))
    if is_admin:
        plan_data.update({"channels": 9999, "videos_per_week": 9999,
                          "custom_prompts": True, "social_posting": True})

    user_obj = {
        "email":   u["email"],
        "name":    u["full_name"] or u["email"],
        "plan":    plan_key,
        "api_key": hashlib.md5(f"ff-{u['id']}".encode()).hexdigest(),
    }

    channels = [dict(r) for r in db.execute(
        "SELECT id, channel_name, youtube_channel_id AS channel_id, niche, "
        "video_type AS voice_style, schedule AS upload_schedule, videos_uploaded "
        "FROM channels WHERE user_id=? AND active=1 ORDER BY created_at DESC",
        (u["id"],)
    ).fetchall()]

    queue = [dict(r) for r in db.execute(
        "SELECT q.*, c.channel_name FROM queue q "
        "LEFT JOIN channels c ON q.channel_id=c.id "
        "WHERE q.user_id=? AND q.status IN ('pending','processing') "
        "ORDER BY q.created_at DESC LIMIT 20",
        (u["id"],)
    ).fetchall()]

    videos = [dict(r) for r in db.execute(
        "SELECT v.*, c.channel_name FROM videos v "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50",
        (u["id"],)
    ).fetchall()]

    social = {}
    for row in db.execute(
        "SELECT sa.* FROM social_accounts sa "
        "JOIN channels c ON sa.channel_id=c.id "
        "WHERE c.user_id=? AND sa.active=1", (u["id"],)
    ).fetchall():
        social.setdefault(row["channel_id"], []).append(dict(row))

    db.close()

    stats = {
        "total":    len(videos),
        "uploaded": sum(1 for v in videos if v["status"] == "uploaded"),
        "channels": len(channels),
        "pending":  len(queue),
    }

    success = "channel_connected" if request.args.get("connected") else ""

    return render_template("dashboard.html",
        plan=plan_data, is_admin=is_admin, plans=PLANS,
        user=user_obj, channels=channels, queue=queue,
        videos=videos, social=social, stats=stats,
        prompts=[], worker_online=bool(celery_app),
        error=request.args.get("error", ""), success=success,
    )

@app.route("/admin")
def admin_page():
    user = get_current_user()
    if not user or not user.get("is_admin"):
        return redirect("/")
    db = get_db()
    total_users  = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_vids   = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    uploaded     = db.execute("SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0]
    total_chans  = db.execute("SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    pro_users    = db.execute("SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0]
    agency_users = db.execute("SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0]
    mrr          = (pro_users * 29) + (agency_users * 99)
    stats_data = {
        "total_users":    total_users,
        "total_videos":   total_vids,
        "uploaded":       uploaded,
        "total_channels": total_chans,
        "pro_users":      pro_users,
        "agency_users":   agency_users,
        "mrr":            mrr,
        "worker_online":  bool(celery_app),
    }
    raw_users = db.execute(
        "SELECT id, email, full_name, plan, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    users_list = []
    for u in raw_users:
        ud = dict(u)
        ud["name"]    = u["full_name"] or ""
        ud["api_key"] = hashlib.md5(f"ff-{u['id']}".encode()).hexdigest()
        users_list.append(ud)
    raw_chans = db.execute(
        "SELECT c.id, c.channel_name, c.youtube_channel_id, c.niche, c.video_type, "
        "c.schedule, c.videos_uploaded, c.created_at, u.email "
        "FROM channels c LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.active=1 ORDER BY c.created_at DESC"
    ).fetchall()
    channels_list = []
    for c in raw_chans:
        cd = dict(c)
        cd["channel_id"]      = c["youtube_channel_id"]
        cd["upload_schedule"] = c["schedule"]
        channels_list.append(cd)
    raw_vids = db.execute(
        "SELECT v.*, u.email, c.channel_name FROM videos v "
        "LEFT JOIN users u ON v.user_id=u.id "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "ORDER BY v.created_at DESC LIMIT 100"
    ).fetchall()
    videos_list  = [dict(r) for r in raw_vids]
    admin_row    = db.execute("SELECT email FROM users WHERE id=?", (user["user_id"],)).fetchone()
    admin_email  = admin_row["email"] if admin_row else ""
    db.close()
    social_keys = {}
    keys_file = "social_keys.json"
    if os.path.exists(keys_file):
        try:
            with open(keys_file) as f:
                social_keys = json.load(f)
        except Exception:
            social_keys = {}
    return render_template("admin.html",
        stats=stats_data, mrr=mrr,
        users=users_list, channels=channels_list,
        videos=videos_list, social_keys=social_keys,
        admin_email=admin_email,
    )

# ── Auth API ──────────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    d         = request.get_json() or {}
    print(f"[REGISTER] Raw payload: {d}")
    email     = d.get("email", "").strip().lower()
    password  = d.get("password", "")
    full_name = d.get("full_name", "") or d.get("name", "")
    print(f"[REGISTER] email={email!r} full_name={full_name!r} password_set={bool(password)}")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO users (email, password_hash, full_name) VALUES (?,?,?)",
                   (email, hash_pw(password), full_name))
        db.commit()
        user  = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        token = make_token(user["id"])
        session["token"] = token
        send_email(email, full_name, "Welcome to FinanceFlow!", f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Welcome to FinanceFlow!</h2>
            <p>Your account is ready. Connect your YouTube channel and we handle everything.</p>
            <a href="{APP_URL}/dashboard" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                Go to Dashboard →
            </a>
            </div>""")
        return jsonify({"token": token, "redirect": "/dashboard"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[REGISTER ERROR] {e}")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500
    finally:
        db.close()

@app.route("/api/auth/login", methods=["POST"])
def login():
    try:
        d        = request.get_json() or {}
        print(f"[LOGIN] Raw payload: {d}")
        email    = d.get("email", "").strip().lower()
        password = d.get("password", "")
        print(f"[LOGIN] email={email!r} password_set={bool(password)}")
        db   = get_db()
        user = db.execute("SELECT * FROM users WHERE email=? AND password_hash=?",
                          (email, hash_pw(password))).fetchone()
        db.close()
        if not user:
            print(f"[LOGIN] No user found for email={email!r}")
            return jsonify({"error": "Invalid email or password"}), 401
        print(f"[LOGIN] Success for user_id={user['id']} is_admin={user['is_admin']}")
        token = make_token(user["id"], bool(user["is_admin"]))
        session["token"] = token
        return jsonify({"token": token, "redirect": "/admin" if user["is_admin"] else "/dashboard"})
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[LOGIN ERROR] {e}")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

@app.route("/api/auth/logout", methods=["POST"])
@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    d     = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    db    = get_db()
    user  = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
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
            <a href="{link}" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                Reset Password →
            </a>
            </div>""")
    db.close()
    return jsonify({"status": "If that email exists, a reset link has been sent"})

@app.route("/api/auth/reset-password", methods=["POST"])
def do_reset_password():
    d        = request.get_json() or {}
    token    = d.get("token", "")
    new_pass = d.get("password", "")
    if not new_pass or len(new_pass) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE reset_token=? AND reset_expires>?",
                      (token, int(time.time()))).fetchone()
    if not user:
        db.close()
        return jsonify({"error": "Invalid or expired reset link"}), 400
    db.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_expires=NULL WHERE id=?",
               (hash_pw(new_pass), user["id"]))
    db.commit(); db.close()
    return jsonify({"status": "Password updated successfully"})

@app.route("/api/auth/me")
@login_required
def me():
    db   = get_db()
    user = db.execute("SELECT id, email, full_name, plan, created_at FROM users WHERE id=?",
                      (request.uid,)).fetchone()
    db.close()
    return jsonify(dict(user)) if user else (jsonify({"error": "Not found"}), 404)

# ── YouTube OAuth ─────────────────────────────────────────────────────────────
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
    except Exception:
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
        item          = yt_data["items"][0]
        channel_name  = item["snippet"]["title"]
        yt_channel_id = item["id"]
    except Exception as e:
        print(f"[OAUTH] YouTube channel fetch failed: {e}")
    db       = get_db()
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

# ── Channel API ───────────────────────────────────────────────────────────────
@app.route("/api/channels")
@login_required
def get_channels():
    db   = get_db()
    rows = db.execute(
        "SELECT id, channel_name, youtube_channel_id, niche, video_type, schedule, videos_uploaded, created_at "
        "FROM channels WHERE user_id=? AND active=1 ORDER BY created_at DESC", (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/channels/<int:cid>", methods=["PUT"])
@login_required
def update_channel(cid):
    d  = request.get_json() or {}
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

# ── Video / Queue API ─────────────────────────────────────────────────────────
@app.route("/api/videos/generate", methods=["POST"])
@login_required
def generate_video():
    d             = request.get_json() or {}
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
    if celery_app:
        process_video_task.delay(job_id)
        return jsonify({"job_id": job_id, "status": "queued", "queue": "celery"})
    return jsonify({"job_id": job_id, "status": "queued", "queue": "sqlite"})

@app.route("/api/videos/generate-script", methods=["POST"])
@login_required
def generate_script_api():
    """Generate a video script without queuing a full job."""
    d          = request.get_json() or {}
    prompt     = d.get("prompt", "")
    niche      = d.get("niche", "personal_finance")
    video_type = d.get("video_type", "short")
    if not prompt and not niche:
        return jsonify({"error": "Provide prompt or niche"}), 400
    script = generate_script(prompt, niche, video_type)
    return jsonify({
        "script":     script,
        "provider":   "openai" if (OPENAI_KEY and HAS_OPENAI) else "built-in",
        "niche":      niche,
        "video_type": video_type,
    })

@app.route("/api/videos/queue")
@login_required
def get_queue():
    db   = get_db()
    rows = db.execute(
        "SELECT q.*, c.channel_name FROM queue q LEFT JOIN channels c ON q.channel_id=c.id "
        "WHERE q.user_id=? ORDER BY q.created_at DESC LIMIT 30", (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/videos/status/<int:job_id>")
@login_required
def job_status(job_id):
    db  = get_db()
    job = db.execute("SELECT * FROM queue WHERE id=? AND user_id=?",
                     (job_id, request.uid)).fetchone()
    db.close()
    return jsonify(dict(job)) if job else (jsonify({"error": "Not found"}), 404)

@app.route("/api/videos")
@login_required
def get_videos():
    db   = get_db()
    rows = db.execute(
        "SELECT v.*, c.channel_name FROM videos v LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50", (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

# ── Social API ────────────────────────────────────────────────────────────────
@app.route("/api/social/<int:cid>")
@login_required
def get_social(cid):
    db   = get_db()
    rows = db.execute("SELECT id, platform, active FROM social_accounts WHERE channel_id=?",
                      (cid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/social/<int:cid>", methods=["POST"])
@login_required
def save_social(cid):
    d           = request.get_json() or {}
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

# ── Stats API ─────────────────────────────────────────────────────────────────
@app.route("/api/stats")
@login_required
def stats():
    db         = get_db()
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

# ── Payment API ───────────────────────────────────────────────────────────────
@app.route("/api/payments/request", methods=["POST"])
@login_required
def payment_request():
    """User requests a plan upgrade — creates pending payment record."""
    d        = request.get_json() or {}
    plan     = d.get("plan", "")
    provider = d.get("provider", "manual")  # manual | stripe | jazzcash | easypaisa | razorpay
    if plan not in PLANS or PLANS[plan]["price"] == 0:
        return jsonify({"error": "Invalid plan or plan is free"}), 400
    amount = PLANS[plan]["price"]
    db     = get_db()
    db.execute("UPDATE payments SET status='cancelled' WHERE user_id=? AND status='pending'",
               (request.uid,))
    payment_id = db.execute(
        "INSERT INTO payments (user_id, amount, plan, provider, status) VALUES (?,?,?,?,'pending')",
        (request.uid, amount, plan, provider)
    ).lastrowid
    db.commit(); db.close()
    resp = {
        "payment_id": payment_id, "plan": plan,
        "amount": amount, "provider": provider, "status": "pending",
    }
    if provider == "stripe" and HAS_STRIPE and STRIPE_KEY:
        resp["instructions"] = "Use /api/payments/stripe-checkout to get a Stripe checkout URL"
    elif provider == "jazzcash":
        resp["instructions"] = f"Send PKR {amount * 280:.0f} to our JazzCash account and submit reference via /api/payments/manual"
    elif provider == "easypaisa":
        resp["instructions"] = f"Send PKR {amount * 280:.0f} to our EasyPaisa account and submit reference via /api/payments/manual"
    elif provider == "razorpay":
        resp["instructions"] = "Integrate with Razorpay order creation and submit reference via /api/payments/manual"
    else:
        resp["instructions"] = f"Transfer ${amount} via bank/wire and submit reference number via /api/payments/manual"
    return jsonify(resp)

@app.route("/api/payments/manual", methods=["POST"])
@login_required
def payment_manual():
    """User submits bank transfer / JazzCash / EasyPaisa reference number."""
    d          = request.get_json() or {}
    reference  = d.get("reference", "").strip()
    payment_id = d.get("payment_id")
    notes      = d.get("notes", "")
    if not reference:
        return jsonify({"error": "Reference number required"}), 400
    db      = get_db()
    payment = None
    if payment_id:
        payment = db.execute(
            "SELECT * FROM payments WHERE id=? AND user_id=? AND status='pending'",
            (payment_id, request.uid)
        ).fetchone()
    if not payment:
        payment = db.execute(
            "SELECT * FROM payments WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
            (request.uid,)
        ).fetchone()
    if not payment:
        db.close()
        return jsonify({"error": "No pending payment found. Use /api/payments/request first"}), 404
    db.execute(
        "UPDATE payments SET reference=?, notes=?, status='submitted', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (reference, notes, payment["id"])
    )
    db.commit()
    admin = db.execute("SELECT email FROM users WHERE is_admin=1 LIMIT 1").fetchone()
    user  = db.execute("SELECT email, full_name FROM users WHERE id=?", (request.uid,)).fetchone()
    db.close()
    if admin:
        send_email(
            admin["email"], "Admin",
            f"💰 New payment submission — {payment['plan']} plan",
            f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">New Payment Submitted</h2>
            <p>User: <b>{user['email']}</b><br>
            Plan: <b>{payment['plan']}</b> (${payment['amount']})<br>
            Reference: <b>{reference}</b><br>
            Notes: {notes or 'none'}</p>
            <a href="{APP_URL}/admin" style="display:inline-block;background:#4F46E5;color:white;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold">
                Review in Admin →
            </a></div>"""
        )
    return jsonify({
        "status":     "submitted",
        "message":    "Reference submitted. Admin will review within 24h.",
        "payment_id": payment["id"],
    })

@app.route("/api/payments/status")
@login_required
def payment_status():
    """User checks their payment history and status."""
    db   = get_db()
    rows = db.execute(
        "SELECT id, amount, plan, provider, status, reference, created_at, updated_at "
        "FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
        (request.uid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/payments/stripe-checkout", methods=["POST"])
@login_required
def stripe_checkout():
    """Create a Stripe Checkout Session for subscription."""
    if not HAS_STRIPE or not STRIPE_KEY:
        return jsonify({"error": "Stripe not configured — set STRIPE_SECRET_KEY"}), 503
    d    = request.get_json() or {}
    plan = d.get("plan", "pro")
    if plan not in PLANS or PLANS[plan]["price"] == 0:
        return jsonify({"error": "Invalid plan"}), 400
    try:
        sess = stripe_lib.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency":     "usd",
                    "product_data": {"name": f"FinanceFlow {PLANS[plan]['name']} Plan"},
                    "recurring":    {"interval": "month"},
                    "unit_amount":  PLANS[plan]["price"] * 100,
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{APP_URL}/dashboard?payment=success",
            cancel_url=f"{APP_URL}/dashboard?payment=cancelled",
            metadata={"user_id": str(request.uid), "plan": plan},
        )
        return jsonify({"checkout_url": sess.url, "session_id": sess.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/payments/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """Stripe webhook — verifies signature, upgrades/downgrades plan."""
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")
    event   = None
    if HAS_STRIPE and STRIPE_WH_SECRET:
        try:
            event = stripe_lib.Webhook.construct_event(payload, sig, STRIPE_WH_SECRET)
        except stripe_lib.error.SignatureVerificationError:
            return jsonify({"error": "Invalid signature"}), 400
    else:
        try:
            event = json.loads(payload)
        except Exception:
            return jsonify({"error": "Invalid payload"}), 400
    etype = event.get("type", "")
    print(f"[STRIPE WEBHOOK] {etype}")
    if etype == "checkout.session.completed":
        sess    = event["data"]["object"]
        user_id = int(sess.get("metadata", {}).get("user_id", 0))
        plan    = sess.get("metadata", {}).get("plan", "pro")
        sub_id  = sess.get("subscription", "")
        if user_id:
            db = get_db()
            db.execute("UPDATE users SET plan=?, stripe_subscription_id=? WHERE id=?",
                       (plan, sub_id, user_id))
            db.execute(
                "INSERT INTO payments (user_id, amount, plan, provider, status, reference) VALUES (?,?,?,'stripe','approved',?)",
                (user_id, PLANS.get(plan, {}).get("price", 0), plan, sub_id)
            )
            db.commit()
            user = db.execute("SELECT email, full_name FROM users WHERE id=?", (user_id,)).fetchone()
            db.close()
            if user:
                send_email(
                    user["email"], user["full_name"],
                    f"✅ You're now on FinanceFlow {plan.title()}!",
                    f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
                    <h2 style="color:#4F46E5">Plan activated!</h2>
                    <p>Your <b>{plan.title()}</b> plan is now live. Enjoy the features!</p>
                    <a href="{APP_URL}/dashboard" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                        Go to Dashboard →
                    </a></div>"""
                )
    elif etype in ("customer.subscription.deleted", "invoice.payment_failed"):
        sub_id = event["data"]["object"].get("id", "")
        if sub_id:
            db = get_db()
            db.execute("UPDATE users SET plan='starter' WHERE stripe_subscription_id=?", (sub_id,))
            db.commit(); db.close()
    return jsonify({"status": "ok"})

# ── Admin payment API ─────────────────────────────────────────────────────────
@app.route("/api/admin/payments")
@admin_required
def admin_payments():
    db   = get_db()
    rows = db.execute(
        "SELECT p.*, u.email, u.full_name FROM payments p "
        "LEFT JOIN users u ON p.user_id=u.id "
        "ORDER BY p.created_at DESC LIMIT 100"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/payments/<int:pid>/approve", methods=["POST"])
@admin_required
def admin_approve_payment(pid):
    db      = get_db()
    payment = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not payment:
        db.close()
        return jsonify({"error": "Payment not found"}), 404
    db.execute("UPDATE payments SET status='approved', updated_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
    db.execute("UPDATE users SET plan=? WHERE id=?", (payment["plan"], payment["user_id"]))
    db.commit()
    user = db.execute("SELECT email, full_name FROM users WHERE id=?", (payment["user_id"],)).fetchone()
    db.close()
    if user:
        send_email(
            user["email"], user["full_name"],
            f"✅ Payment approved — You're now on {payment['plan'].title()}!",
            f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Payment Approved!</h2>
            <p>Your <b>{payment['plan'].title()}</b> plan is now active. Thank you!</p>
            <a href="{APP_URL}/dashboard" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                Go to Dashboard →
            </a></div>"""
        )
    return jsonify({"status": "approved", "plan": payment["plan"], "user_id": payment["user_id"]})

@app.route("/api/admin/payments/<int:pid>/reject", methods=["POST"])
@admin_required
def admin_reject_payment(pid):
    d       = request.get_json() or {}
    reason  = d.get("reason", "Payment could not be verified")
    db      = get_db()
    payment = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not payment:
        db.close()
        return jsonify({"error": "Payment not found"}), 404
    db.execute(
        "UPDATE payments SET status='rejected', notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (reason, pid)
    )
    db.commit()
    user = db.execute("SELECT email, full_name FROM users WHERE id=?", (payment["user_id"],)).fetchone()
    db.close()
    if user:
        send_email(
            user["email"], user["full_name"],
            "Payment not approved — action required",
            f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#ef4444">Payment Not Approved</h2>
            <p>Reason: {reason}</p>
            <p>Please contact support or resubmit with the correct reference.</p></div>"""
        )
    return jsonify({"status": "rejected"})

# ── Admin API ─────────────────────────────────────────────────────────────────
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
    db            = get_db()
    total_users   = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_vids    = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    uploaded      = db.execute("SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0]
    total_chans   = db.execute("SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    pro           = db.execute("SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0]
    agency        = db.execute("SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0]
    queue_pending = db.execute("SELECT COUNT(*) FROM queue WHERE status IN ('pending','processing')").fetchone()[0]
    pending_pays  = db.execute("SELECT COUNT(*) FROM payments WHERE status IN ('pending','submitted')").fetchone()[0]
    db.close()
    return jsonify({
        "total_users":      total_users,
        "total_videos":     total_vids,
        "uploaded":         uploaded,
        "total_channels":   total_chans,
        "mrr":              (pro * 29) + (agency * 99),
        "pro_users":        pro,
        "agency_users":     agency,
        "queue_pending":    queue_pending,
        "pending_payments": pending_pays,
        "worker_online":    bool(celery_app),
    })

@app.route("/api/admin/users")
@admin_required
def admin_users():
    db   = get_db()
    rows = db.execute(
        "SELECT id, email, full_name, plan, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/users/<int:uid>/plan", methods=["PUT", "POST"])
@admin_required
def admin_set_plan(uid):
    d  = request.get_json() or {}
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
    db   = get_db()
    rows = db.execute(
        "SELECT c.*, u.email FROM channels c LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.active=1 ORDER BY c.created_at DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/videos")
@admin_required
def admin_videos():
    db   = get_db()
    rows = db.execute(
        "SELECT v.*, u.email, c.channel_name FROM videos v "
        "LEFT JOIN users u ON v.user_id=u.id "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "ORDER BY v.created_at DESC LIMIT 100"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/social-keys", methods=["POST"])
@admin_required
def admin_save_social_keys():
    d         = request.get_json() or {}
    platform  = d.get("platform", "")
    creds     = d.get("creds", {})
    keys_file = "social_keys.json"
    try:
        existing = {}
        if os.path.exists(keys_file):
            with open(keys_file) as f:
                existing = json.load(f)
        existing[platform] = creds
        with open(keys_file, "w") as f:
            json.dump(existing, f)
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Health ────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({
        "status":  "ok",
        "service": "FinanceFlow SaaS",
        "jwt":     HAS_JWT,
        "openai":  bool(OPENAI_KEY and HAS_OPENAI),
        "stripe":  bool(STRIPE_KEY and HAS_STRIPE),
        "celery":  bool(celery_app),
        "queue":   "celery+redis" if celery_app else "sqlite",
    })

init_db()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
