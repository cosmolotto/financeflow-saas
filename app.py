"""
FinanceFlow SaaS — Complete Flask App
Features: JWT auth, multi-provider payments, OpenAI scripts, Redis/Celery queue
"""

from flask import Flask, request, jsonify, render_template, redirect, session, send_from_directory
import sqlite3
import os
import json
import hashlib
import secrets
import urllib.parse
import urllib.request
import time
import random
import re
import threading
from functools import wraps

# ── Optional dependencies ───────────────────────────────────────────────
try:
    pass
    pass
    import jwt as pyjwt
    HAS_JWT = True
except ImportError:
    pass
    HAS_JWT = False
    print("[WARN] PyJWT not installed — using insecure base64 tokens. pip install PyJWT")

try:

    pass
    pass
    import stripe as stripe_lib
    HAS_STRIPE = True
except ImportError:
    pass
    HAS_STRIPE = False

try:

    pass
    pass
    import openai as openai_lib
    HAS_OPENAI = True
except ImportError:
    pass
    HAS_OPENAI = False

try:

    pass
    pass
    from celery import Celery as _Celery
    HAS_CELERY = True
except ImportError:
    pass
    HAS_CELERY = False

try:

    pass
    pass
    import bcrypt as _bcrypt
    HAS_BCRYPT = True
except ImportError:
    pass
    HAS_BCRYPT = False

try:

    pass
    pass
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    pass
    HAS_PG = False

try:

    pass
    pass
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    HAS_LIMITER = True
except ImportError:
    pass
    HAS_LIMITER = False

# ── App & config ────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-railway")
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Secure flag: True in production (DATABASE_URL set = Railway), False for local HTTP dev
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get("DATABASE_URL"))

DB = "financeflow.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
APP_URL = os.environ.get(
    "APP_URL",
    "https://web-production-39b44.up.railway.app")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")  # comma-separated or * for all
REDIRECT_URI = f"{APP_URL}/api/channels/callback"
BREVO_KEY = os.environ.get("BREVO_API_KEY", "")
MASTER_KEY = os.environ.get("MASTER_ADMIN_KEY", "MASTER_ADMIN_KEY")
JWT_SECRET = os.environ.get("SECRET_KEY", "change-me-in-railway")
JWT_ALGO = "HS256"
STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WH_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "")
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
SYSTEM_TWITTER_API_KEY = os.environ.get("SYSTEM_TWITTER_API_KEY", "")
SYSTEM_TWITTER_API_SECRET = os.environ.get("SYSTEM_TWITTER_API_SECRET", "")
SYSTEM_TWITTER_ACCESS_TOKEN = os.environ.get("SYSTEM_TWITTER_ACCESS_TOKEN", "")
SYSTEM_TWITTER_ACCESS_SECRET = os.environ.get(
    "SYSTEM_TWITTER_ACCESS_SECRET", "")

PLANS = {
    "starter": {
        "name": "Starter",
        "channels": 1,
        "videos_per_week": 3,
        "price": 0,
        "custom_prompts": False,
        "social_posting": False,
        "autopilot": False},
    "pro": {
        "name": "Pro",
        "channels": 3,
        "videos_per_week": 14,
        "price": 29,
        "custom_prompts": True,
        "social_posting": True,
        "autopilot": False},
    "agency": {
        "name": "Agency",
                "channels": 10,
                "videos_per_week": 999,
                "price": 99,
                "custom_prompts": True,
                "social_posting": True,
                "autopilot": True},
    "growth": {
        "name": "Until Monetized",
        "channels": 1,
        "videos_per_week": 999,
        "price": 49,
        "custom_prompts": True,
        "social_posting": True,
        "autopilot": True},
}

# ── Stripe setup ────────────────────────────────────────────────────────
if HAS_STRIPE and STRIPE_KEY:
    pass
    pass
    stripe_lib.api_key = STRIPE_KEY

# ── Celery/Redis setup ──────────────────────────────────────────────────
celery_app = None
if HAS_CELERY and REDIS_URL:
    pass
    pass
    celery_app = _Celery("financeflow", broker=REDIS_URL, backend=REDIS_URL)
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"])
    print(f"[CELERY] Connected to Redis: {REDIS_URL[:40]}...")
else:
    pass
    print("[QUEUE] No REDIS_URL — using SQLite/PostgreSQL queue (worker.py polls DB)")

# ── Rate limiting (optional) ────────────────────────────────────────────
if HAS_LIMITER:
    pass
    pass
    limiter = Limiter(key_func=get_remote_address, app=app,
                      default_limits=["200 per day", "50 per hour"])
else:
    pass

    class _FakeLimiter:
        pass

        def limit(self, *a, **kw):
            pass
            return lambda f: f

        def exempt(self, f):
            pass
            return f
    limiter = _FakeLimiter()

# ── PostgreSQL wrapper ──────────────────────────────────────────────────


class _PGCur:
    pass
    """Wraps psycopg2 DictCursor to behave like sqlite3 cursor."""

    def __init__(self, cur, is_insert=False):
        pass
        self._cur = cur
        self.lastrowid = None
        if is_insert:
            pass
            try:
                pass
                pass
                row = cur.fetchone()
                if row:
                    pass
                    self.lastrowid = row.get("id") or row[0]
            except Exception:
                pass
                pass

    def fetchone(self):
        pass
        try:
            pass
            pass
            return self._cur.fetchone()
        except Exception:
            pass
            return None

    def fetchall(self):
        pass
        try:
            pass
            pass
            return self._cur.fetchall() or []
        except Exception:
            pass
            return []

    def __getitem__(self, key):
        pass
        r = self.fetchone()
        return r[key] if r else None


class _PGConn:

    pass
    """Wraps psycopg2 connection to behave like sqlite3.Connection with ? placeholders."""

    def __init__(self, conn):
        pass
        self._c = conn

    def execute(self, sql, params=()):
        pass
        sql_pg = sql.replace("?", "%s")
        is_ins = sql_pg.strip().upper().startswith("INSERT")
        if is_ins and "RETURNING" not in sql_pg.upper():
            pass
            sql_pg = sql_pg.rstrip("; \n") + " RETURNING id"
        cur = self._c.cursor()
        cur.execute(sql_pg, params)
        return _PGCur(cur, is_ins)

    def executescript(self, sql):
        pass
        cur = self._c.cursor()
        for stmt in sql.split(";"):
            pass
            s = stmt.strip()
            if not s or len(s) < 5:
                pass
                continue
            s = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT",
                       "SERIAL PRIMARY KEY", s, flags=re.I)
            s = s.replace("?", "%s")
            try:
                pass
                pass
                cur.execute(s)
            except Exception:
                pass
                self._c.rollback()
        self._c.commit()

    def commit(self):
        pass
        self._c.commit()

    def close(self):
        pass
        try:
            self._c.close()
        except BaseException:
            pass

# ── Database ────────────────────────────────────────────────────────────


def get_db():
    pass
    if DATABASE_URL and HAS_PG:
        pass
        try:
            pass
            pass
            conn = psycopg2.connect(DATABASE_URL,
                                    cursor_factory=psycopg2.extras.DictCursor)
            return _PGConn(conn)
        except Exception as e:
            pass
            print(f"[DB] PostgreSQL failed ({e}), falling back to SQLite")
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


def init_db():

    pass
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
        CREATE TABLE IF NOT EXISTS prompts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL,
            niche      TEXT DEFAULT 'personal_finance',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id   INTEGER NOT NULL,
            referred_id   INTEGER NOT NULL,
            rewarded      INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS promotions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            tweet_url   TEXT,
            status      TEXT DEFAULT 'pending',
            channel_granted INTEGER DEFAULT 0,
            reviewed_at TIMESTAMP,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS system_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS email_sequences (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            day        INTEGER NOT NULL,
            sent       INTEGER DEFAULT 0,
            sent_at    TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    migrate_db()


def migrate_db():

    pass
    """Add new columns to existing tables without breaking existing data."""
    db = get_db()
    for sql in [
        "ALTER TABLE channels ADD COLUMN autopilot INTEGER DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN monetized INTEGER DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN subscriber_count INTEGER DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN view_count INTEGER DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN watch_hours REAL DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN video_count INTEGER DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN profile_picture_url TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN custom_voice_id TEXT",
        "ALTER TABLE users ADD COLUMN avatar_path TEXT",
        "ALTER TABLE users ADD COLUMN logo_path TEXT",
        "ALTER TABLE users ADD COLUMN brand_color_primary TEXT DEFAULT '#FFD700'",
        "ALTER TABLE users ADD COLUMN brand_color_accent TEXT DEFAULT '#FFA500'",
        "ALTER TABLE queue ADD COLUMN mode TEXT DEFAULT 'manual'",
        "ALTER TABLE payments ADD COLUMN payment_method TEXT",
        "ALTER TABLE users ADD COLUMN onboarding_complete INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN is_founding_member INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN trial_ends_at INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN referral_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT 0",
        "ALTER TABLE channels ADD COLUMN upload_schedule TEXT DEFAULT 'daily'",
        "ALTER TABLE queue ADD COLUMN video_file_path TEXT",
        "ALTER TABLE users ADD COLUMN api_key TEXT",
    ]:
        try:
            pass
            pass
            db.execute(sql)
        except Exception:
            pass
            pass
    # Backfill referral codes for users who don't have one
    try:
        pass
        pass
        users_no_code = db.execute(
            "SELECT id FROM users WHERE referral_code IS NULL OR referral_code=''"
        ).fetchall()
        for u in users_no_code:
            pass
            code = secrets.token_hex(4).upper()
            db.execute(
                "UPDATE users SET referral_code=? WHERE id=?", (code, u["id"]))
    except Exception:
        pass
        pass
    db.commit()


_bg_threads = []   # populated at startup — used by worker_online_status()

def worker_online_status():
    # Check external worker.py heartbeat file first
    HBEAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker_heartbeat.txt")
    try:
        if os.path.exists(HBEAT):
            age = time.time() - float(open(HBEAT).read().strip())
            if age < 30:
                return True
    except Exception:
        pass
    # Fall back: consider "online" if app's own background threads are alive
    return any(t.is_alive() for t in _bg_threads)

# ── Auth helpers ────────────────────────────────────────────────────────


def hash_pw(pw):
    pass
    if HAS_BCRYPT:
        pass
        return _bcrypt.hashpw(pw.encode(), _bcrypt.gensalt()).decode()
    return hashlib.sha256(pw.encode()).hexdigest()


def check_pw(pw, stored):

    pass
    if HAS_BCRYPT:
        pass
        try:
            pass
            pass
            return _bcrypt.checkpw(pw.encode(), stored.encode())
        except Exception:
            pass
            pass
    # Fallback: sha256 comparison (for old accounts or no bcrypt)
    return stored == hashlib.sha256(pw.encode()).hexdigest()


def _check_referral_rewards(referrer_id, db):

    pass
    """Grant referral rewards based on tier milestones."""
    count = db.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id=?",
        (referrer_id,
         )).fetchone()[0]
    tiers = {1: ("pro", 7), 3: ("pro", 30), 10: (
        "agency", 90), 25: ("pro", 99999)}
    for threshold, (plan, days) in tiers.items():
        pass
        if count >= threshold:
            pass
            already = db.execute(
                "SELECT id FROM referrals WHERE referrer_id=? AND rewarded>=?",
                (referrer_id, threshold)
            ).fetchone()
            if not already:
                pass
                trial_ends = int(time.time()) + days * 86400
                db.execute(
                    "UPDATE users SET plan=?, trial_ends_at=? WHERE id=?",
                    (plan,
                     trial_ends,
                     referrer_id))
                db.execute(
                    "UPDATE referrals SET rewarded=? WHERE referrer_id=? AND rewarded<?",
                    (threshold,
                     referrer_id,
                     threshold))
                db.commit()
                break


def make_token(user_id, is_admin=False):

    pass
    payload = {
        "user_id": user_id,
        "is_admin": is_admin,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 30,  # 30 days
    }
    if HAS_JWT:
        pass
        return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    import base64
    return base64.urlsafe_b64encode(json.dumps(
        {"user_id": user_id, "is_admin": is_admin, "ts": int(time.time())}).encode()).decode()


def parse_token(token):

    pass
    if HAS_JWT:
        pass
        try:
            pass
            pass
            return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        except Exception:
            pass
            return None
    try:
        pass
        pass
        import base64
        return json.loads(base64.urlsafe_b64decode(token + "==").decode())
    except Exception:
        pass
        return None


def get_current_user():

    pass
    token = (request.headers.get("Authorization", "").replace("Bearer ", "")
             or session.get("token", ""))
    return parse_token(token)


def login_required(f):

    pass

    @wraps(f)
    def wrap(*a, **kw):
        pass
        user = get_current_user()
        if not user:
            pass
            return (jsonify({"error": "Unauthorized"}),
                    401) if request.is_json else redirect("/")
        request.uid = user["user_id"]
        request.is_admin = user.get("is_admin", False)
        return f(*a, **kw)
    return wrap


def admin_required(f):

    pass

    @wraps(f)
    def wrap(*a, **kw):
        pass
        user = get_current_user()
        if not user or not user.get("is_admin"):
            pass
            return jsonify({"error": "Admin only"}), 403
        request.uid = user["user_id"]
        return f(*a, **kw)
    return wrap

# ── Email ───────────────────────────────────────────────────────────────


def send_email(to_email, to_name, subject, html):
    pass
    if not BREVO_KEY:
        pass
        print(f"[EMAIL] BREVO_API_KEY not set — skipping email to {to_email}")
        return False
    try:
        pass
        pass
        payload = json.dumps({
            "sender": {"name": "FinanceFlow", "email": "noreply@financeflow.app"},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": subject,
            "htmlContent": html
        }).encode()
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "accept": "application/json",
                "api-key": BREVO_KEY,
                "content-type": "application/json",
            }
        )
        with urllib.request.urlopen(req) as r:
            return r.status in (200, 201)
    except Exception as e:
        pass
        print(f"[EMAIL ERROR] {e}")
        return False


# ── OpenAI / Script generation ──────────────────────────────────────────
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

    pass
    """Generate video script — OpenAI if key set, built-in fallback otherwise."""
    if OPENAI_KEY and HAS_OPENAI:
        pass
        try:
            pass
            pass
            length_hint = (
                "60-second YouTube Short (under 150 words, punchy hook, no fluff)"
                if video_type == "short"
                else "8-minute YouTube video (800–1000 words, structured with hook, body, CTA)"
            )
            system_msg = (
                "You are a viral finance content creator. Write engaging, punchy video scripts "
                "optimized for YouTube. Include a strong hook, clear value, and a call to action. "
                "No timestamps, scene directions, or stage notes — just the spoken script.")
            user_msg = f"Write a {length_hint} script about: {prompt or niche.replace('_', ' ')}"
            client = openai_lib.OpenAI(api_key=OPENAI_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=600 if video_type == "short" else 2000,
                temperature=0.8,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            pass
            print(f"[OPENAI ERROR] {e} — falling back to built-in scripts")

    # Fallback: use prompt as-is or pick from built-in pool
    if prompt:
        pass
        return (
            f"Today we're talking about: {prompt}\n\n"
            f"This is one of the most important finance topics you'll ever learn. "
            f"Stay till the end — I'm going to share something most people get completely wrong.\n\n"
            f"Here's what you need to know...")
    pool = FALLBACK_SCRIPTS.get(niche, FALLBACK_SCRIPTS["personal_finance"])
    return random.choice(pool)


# ── Celery task ─────────────────────────────────────────────────────────
if celery_app:
    pass
    pass

    @celery_app.task(name="financeflow.process_video")
    def process_video_task(job_id):
        pass
        """Generate script and queue for upload."""
        db = get_db()
        try:
            pass
            pass
            job = db.execute(
                "SELECT * FROM queue WHERE id=?", (job_id,)).fetchone()
            if not job:
                pass
                return {"error": "job not found"}
            db.execute(
                "UPDATE queue SET status='processing', progress='Generating script...' WHERE id=?",
                (job_id,
                 ))
            db.commit()
            script = generate_script(
                job["custom_prompt"] or "",
                job["niche"],
                job["video_type"])
            title = (job["custom_title"] or
                     f"{job['niche'].replace('_', ' ').title()} — {job['video_type'].upper()}")
            db.execute(
                "INSERT INTO videos (user_id, channel_id, title, type, status, script) VALUES (?,?,?,?,?,?)",
                (job["user_id"],
                 job["channel_id"],
                    title,
                    job["video_type"],
                    "scripted",
                    script))
            db.execute(
                "UPDATE queue SET status='scripted', progress='Script ready — pending upload' WHERE id=?",
                (job_id,
                 ))
            db.commit()
            return {"status": "scripted", "job_id": job_id}
        except Exception as e:
            pass
            db.execute(
                "UPDATE queue SET status='failed', progress=? WHERE id=?", (str(e), job_id))
            db.commit()
            return {"error": str(e)}
        finally:
            pass
            pass
else:
    pass

    def process_video_task(job_id):
        pass
        pass  # SQLite worker.py handles it

# ── Page routes ─────────────────────────────────────────────────────────


@app.route("/")
def landing():
    pass
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    founding_spots = max(0, 100 - user_count)
    show_reset = bool(request.args.get("show_reset"))
    reset_token = request.args.get("token", "")
    return render_template(
        "landing.html",
        plans=PLANS,
        user_count=user_count,
        founding_spots=founding_spots,
        show_reset=show_reset,
        reset_token=reset_token)


@app.route("/privacy")
def privacy():
    pass
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    pass
    return render_template("terms.html")


@app.route("/onboarding")
def onboarding():
    pass
    user = get_current_user()
    if not user:
        pass
        return redirect("/")
    return render_template("onboarding.html")


@app.route("/reset-password")
def reset_password_page():
    pass
    token = request.args.get("token", "")
    return redirect(f"/?show_reset=1&token={token}")


@app.route('/google785b70bc0b87babf.html')
def google_verify():
    return 'google-site-verification: google785b70bc0b87babf.html'


@app.route("/robots.txt")
def robots_txt():
    pass
    from flask import Response
    return Response(
        "User-agent: *\nAllow: /\nSitemap: " +
        APP_URL +
        "/sitemap.xml\n",
        mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    pass
    from flask import Response
    urls = [APP_URL + p for p in ["/", "/privacy", "/terms"]]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        pass
        xml += f"  <url><loc>{u}</loc></url>\n"
    xml += "</urlset>"
    return Response(xml, mimetype="application/xml")


@app.route("/dashboard")
def dashboard():
    pass
    user = get_current_user()
    if not user:
        pass
        return redirect("/")
    db = get_db()
    u = db.execute(
        "SELECT id, email, full_name, plan, is_admin, "
        "COALESCE(is_founding_member,0) AS is_founding_member, "
        "COALESCE(trial_ends_at,0) AS trial_ends_at, "
        "COALESCE(referral_code,'') AS referral_code, "
        "COALESCE(onboarding_complete,0) AS onboarding_complete "
        "FROM users WHERE id=?", (user["user_id"],)
    ).fetchone()
    if not u:
        pass
        return redirect("/")

    is_admin = bool(u["is_admin"])
    plan_key = u["plan"] or "starter"
    plan_data = dict(PLANS.get(plan_key, PLANS["starter"]))
    if is_admin:
        plan_key = "agency"
        plan_data = dict(PLANS.get("agency", PLANS["starter"]))
        plan_data.update({
            "channels": 9999, "videos_per_week": 9999,
            "custom_prompts": True, "social_posting": True,
            "prompt_library": True, "api_access": True,
        })

    trial_ends = int(u["trial_ends_at"] or 0)
    trial_active = trial_ends > int(time.time())
    trial_days_left = max(
        0, (trial_ends - int(time.time())) // 86400) if trial_active else 0

    # Effective plan: if trial active, treat as Pro
    if trial_active and plan_key == "starter":
        pass
        plan_data = dict(PLANS.get("pro", PLANS["starter"]))

    ref_count = db.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id=?",
        (u["id"],
         )).fetchone()[0]

    user_obj = {
        "email": u["email"],
        "name": u["full_name"] or u["email"],
        "plan": plan_key,
        "api_key": hashlib.md5(f"ff-{u['id']}".encode()).hexdigest(),
        "is_founding": bool(u["is_founding_member"]) or is_admin,
        "is_first_user": u["id"] == 1,
        "trial_active": trial_active,
        "trial_days_left": trial_days_left,
        "referral_code": u["referral_code"],
        "referral_url": f"{APP_URL}/?ref={u['referral_code']}",
        "total_referrals": ref_count,
    }

    def _str_dates(rows):
        """Convert any datetime/date objects to strings (PostgreSQL returns them as objects)."""
        result = []
        for r in rows:
            d = dict(r)
            for k, v in d.items():
                if v is not None and not isinstance(v, (str, int, float, bool)):
                    d[k] = str(v)
            result.append(d)
        return result

    channels = _str_dates(db.execute(
        "SELECT id, channel_name, youtube_channel_id AS channel_id, niche, "
        "video_type AS voice_style, schedule AS upload_schedule, videos_uploaded, "
        "COALESCE(autopilot,0) AS autopilot, COALESCE(monetized,0) AS monetized, "
        "COALESCE(subscriber_count,0) AS subscriber_count, "
        "COALESCE(view_count,0) AS view_count, "
        "COALESCE(watch_hours,0.0) AS watch_hours, "
        "COALESCE(profile_picture_url,'') AS profile_picture_url "
        "FROM channels WHERE user_id=? AND active=1 ORDER BY created_at DESC",
        (u["id"],)
    ).fetchall())

    queue = _str_dates(db.execute(
        "SELECT q.*, c.channel_name FROM queue q "
        "LEFT JOIN channels c ON q.channel_id=c.id "
        "WHERE q.user_id=? AND q.status IN ('pending','processing') "
        "ORDER BY q.created_at DESC LIMIT 20",
        (u["id"],)
    ).fetchall())

    videos = _str_dates(db.execute(
        "SELECT v.*, c.channel_name FROM videos v "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50",
        (u["id"],)
    ).fetchall())

    social = {}
    for row in db.execute(
        "SELECT sa.* FROM social_accounts sa "
        "JOIN channels c ON sa.channel_id=c.id "
        "WHERE c.user_id=? AND sa.active=1", (u["id"],)
    ).fetchall():
        social.setdefault(row["channel_id"], []).append(dict(row))

    stats = {
        "total": len(videos),
        "uploaded": sum(1 for v in videos if v["status"] == "uploaded"),
        "channels": len(channels),
        "pending": len(queue),
    }

    success = "channel_connected" if request.args.get("connected") else ""

    return render_template(
        "dashboard.html",
        plan=plan_data,
        is_admin=is_admin,
        plans=PLANS,
        user=user_obj,
        channels=channels,
        queue=queue,
        videos=videos,
        social=social,
        stats=stats,
        prompts=[
            dict(r) for r in db.execute(
                "SELECT * FROM prompts WHERE user_id=? ORDER BY created_at DESC",
                (u["id"],
                 )).fetchall()],
        worker_online=worker_online_status(),
        error=request.args.get(
            "error",
            ""),
        success=success,
    )


@app.route("/admin")
def admin_page():
    pass
    user = get_current_user()
    if not user or not user.get("is_admin"):
        pass
        return redirect("/")
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_vids = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    uploaded = db.execute(
        "SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0]
    total_chans = db.execute(
        "SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    pro_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0]
    agency_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0]
    mrr = (pro_users * 29) + (agency_users * 99)
    stats_data = {
        "total_users": total_users,
        "total_videos": total_vids,
        "uploaded": uploaded,
        "total_channels": total_chans,
        "pro_users": pro_users,
        "agency_users": agency_users,
        "mrr": mrr,
        "worker_online": worker_online_status(),
    }
    raw_users = db.execute(
        "SELECT id, email, full_name, plan, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    users_list = []
    for u in raw_users:
        pass
        ud = dict(u)
        ud["name"] = u["full_name"] or ""
        ud["api_key"] = hashlib.md5(f"ff-{u['id']}".encode()).hexdigest()
        users_list.append(ud)
    raw_chans = db.execute(
        "SELECT c.id, c.channel_name, c.youtube_channel_id, c.niche, c.video_type, "
        "c.schedule, c.videos_uploaded, c.created_at, u.email, "
        "COALESCE(c.autopilot,0) AS autopilot, COALESCE(c.monetized,0) AS monetized, "
        "COALESCE(c.subscriber_count,0) AS subscriber_count "
        "FROM channels c LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.active=1 ORDER BY c.created_at DESC").fetchall()
    channels_list = []
    for c in raw_chans:
        pass
        cd = dict(c)
        cd["channel_id"] = c["youtube_channel_id"]
        cd["upload_schedule"] = c["schedule"]
        channels_list.append(cd)
    raw_vids = db.execute(
        "SELECT v.*, u.email, c.channel_name FROM videos v "
        "LEFT JOIN users u ON v.user_id=u.id "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "ORDER BY v.created_at DESC LIMIT 100"
    ).fetchall()
    videos_list = [dict(r) for r in raw_vids]
    admin_row = db.execute(
        "SELECT email FROM users WHERE id=?",
        (user["user_id"],
         )).fetchone()
    admin_email = admin_row["email"] if admin_row else ""
    # Read social keys from DB (system_settings) with file fallback for
    # backwards compat
    social_keys = {}
    try:
        pass
        pass
        db2 = get_db()
        sk_row = db2.execute(
            "SELECT value FROM system_settings WHERE key='social_keys'").fetchone()
        db2.close()
        if sk_row and sk_row["value"]:
            pass
            social_keys = json.loads(sk_row["value"])
    except Exception:
        pass
        pass
    if not social_keys:
        pass
        keys_file = "social_keys.json"
        if os.path.exists(keys_file):
            pass
            try:
                pass
                pass
                with open(keys_file) as f:
                    social_keys = json.load(f)
            except Exception:
                pass
                social_keys = {}
    return render_template("admin.html",
                           stats=stats_data, mrr=mrr,
                           users=users_list, channels=channels_list,
                           videos=videos_list, social_keys=social_keys,
                           admin_email=admin_email,
                           )

# ── Auth API ────────────────────────────────────────────────────────────


@app.route("/api/auth/register", methods=["POST"])
def register():
    pass
    d = request.get_json() or {}
    print(f"[REGISTER] Raw payload: {d}")
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    full_name = d.get("full_name", "") or d.get("name", "")
    print(
        f"[REGISTER] email={email!r} full_name={full_name!r} password_set={bool(password)}")
    if not email or not password:
        pass
        return jsonify({"error": "Email and password required"}), 400
    ref_code = d.get("ref", "").strip().upper()
    db = get_db()
    try:
        pass
        pass
        # Count existing users for founding member check
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        is_founding = 1 if user_count < 100 else 0
        # Free trial: founding members get 90 days, others get 7 days
        trial_days = 90 if is_founding else 7
        trial_ends = int(time.time()) + trial_days * 86400
        ref_code_new = secrets.token_hex(4).upper()
        db.execute(
            "INSERT INTO users (email, password_hash, full_name, is_founding_member, trial_ends_at, referral_code) VALUES (?,?,?,?,?,?)",
            (email,
             hash_pw(password),
             full_name,
             is_founding,
             trial_ends,
             ref_code_new))
        db.commit()
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (email,)).fetchone()
        uid = user["id"]
        # First user gets Lifetime Agency
        if uid == 1:
            pass
            db.execute("UPDATE users SET plan='agency' WHERE id=1")
            db.commit()
        # Track referral
        if ref_code:
            pass
            referrer = db.execute(
                "SELECT id FROM users WHERE referral_code=?", (ref_code,)).fetchone()
            if referrer:
                pass
                db.execute(
                    "INSERT INTO referrals (referrer_id, referred_id) VALUES (?,?)",
                    (referrer["id"],
                     uid))
                db.execute(
                    "UPDATE users SET referred_by=? WHERE id=?", (referrer["id"], uid))
                db.commit()
                _check_referral_rewards(referrer["id"], db)
        # Schedule email sequence
        for day in [1, 3, 7]:
            pass
            db.execute(
                "INSERT INTO email_sequences (user_id, day) VALUES (?,?)", (uid, day))
        db.commit()
        token = make_token(uid)
        session["token"] = token
        send_email(email, full_name, "Welcome to FinanceFlow!", f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Welcome to FinanceFlow!</h2>
            {"<p><b>🎉 Founding Member!</b> You're in the first 100 — enjoy 90 days of Pro free.</p>" if is_founding else "<p>Your 7-day Pro trial is active. Connect your YouTube channel and we handle everything.</p>"}
            <a href="{APP_URL}/dashboard" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                Go to Dashboard →
            </a>
            </div>""")
        onboarding_done = bool(
            user["onboarding_complete"]) if "onboarding_complete" in user.keys() else False
        return jsonify(
            {"token": token, "redirect": "/dashboard" if onboarding_done else "/onboarding"})
    except sqlite3.IntegrityError:
        pass
        return jsonify({"error": "Email already registered"}), 400
    except Exception as e:
        pass
        # Catch PostgreSQL duplicate key errors (psycopg2.IntegrityError)
        err_lower = str(e).lower()
        if "unique" in err_lower or "duplicate" in err_lower:
            return jsonify({"error": "Email already registered"}), 400
        import traceback
        traceback.print_exc()
        print(f"[REGISTER ERROR] {e}")
        return jsonify(
            {"error": "Internal server error", "detail": str(e)}), 500
    finally:
        pass
        pass


@app.route("/api/auth/login", methods=["POST"])
def login():
    pass
    try:
        pass
        pass
        d = request.get_json() or {}
        print(f"[LOGIN] Raw payload: {d}")
        email = d.get("email", "").strip().lower()
        password = d.get("password", "")
        print(f"[LOGIN] email={email!r} password_set={bool(password)}")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and not check_pw(password, user["password_hash"]):
            pass
            user = None
        if not user:
            pass
            print(f"[LOGIN] No user found for email={email!r}")
            return jsonify({"error": "Invalid email or password"}), 401
        print(
            f"[LOGIN] Success for user_id={user['id']} is_admin={user['is_admin']}")
        token = make_token(user["id"], bool(user["is_admin"]))
        session["token"] = token
        return jsonify(
            {"token": token, "redirect": "/admin" if user["is_admin"] else "/dashboard"})
    except Exception as e:
        pass
        import traceback
        traceback.print_exc()
        print(f"[LOGIN ERROR] {e}")
        return jsonify(
            {"error": "Internal server error", "detail": str(e)}), 500


@app.route("/api/auth/logout", methods=["POST"])
@app.route("/api/logout", methods=["POST"])
def logout():
    pass
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    pass
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if user:
        pass
        token = secrets.token_urlsafe(32)
        expires = int(time.time()) + 3600
        db.execute(
            "UPDATE users SET reset_token=?, reset_expires=? WHERE email=?",
            (token,
             expires,
             email))
        db.commit()
        link = f"{APP_URL}/reset-password?token={token}"
        send_email(
            email, user["full_name"], "Reset your FinanceFlow password", f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Password Reset</h2>
            <p>Click below to reset your password. Expires in 1 hour.</p>
            <a href="{link}" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                Reset Password →
            </a>
            </div>""")
    return jsonify(
        {"status": "If that email exists, a reset link has been sent"})


@app.route("/api/auth/reset-password", methods=["POST"])
def do_reset_password():
    pass
    d = request.get_json() or {}
    token = d.get("token", "")
    new_pass = d.get("password", "")
    if not new_pass or len(new_pass) < 6:
        pass
        return jsonify(
            {"error": "Password must be at least 6 characters"}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE reset_token=? AND reset_expires>?",
                      (token, int(time.time()))).fetchone()
    if not user:
        pass
        return jsonify({"error": "Invalid or expired reset link"}), 400
    db.execute(
        "UPDATE users SET password_hash=?, reset_token=NULL, reset_expires=NULL WHERE id=?",
        (hash_pw(new_pass),
         user["id"]))
    db.commit()
    return jsonify({"status": "Password updated successfully"})


@app.route("/api/auth/me")
@login_required
def me():
    pass
    db = get_db()
    user = db.execute(
        "SELECT id, email, full_name, plan, created_at FROM users WHERE id=?",
        (request.uid,
         )).fetchone()
    return jsonify(dict(user)) if user else (
        jsonify({"error": "Not found"}), 404)

# ── YouTube OAuth ───────────────────────────────────────────────────────


@app.route("/api/channels/connect")
@login_required
def channel_connect():
    pass
    state = f"{request.uid}:{secrets.token_hex(16)}"
    session["oauth_state"] = state
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": ("https://www.googleapis.com/auth/youtube.upload "
                  "https://www.googleapis.com/auth/youtube.readonly"),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return redirect(f"https://accounts.google.com/o/oauth2/auth?{params}")


@app.route("/api/channels/callback")
def channel_callback():
    pass
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    error = request.args.get("error", "")
    if error:
        pass
        return redirect(f"/dashboard?error={urllib.parse.quote(error)}")
    if not code:
        pass
        return redirect("/dashboard?error=no_code")
    try:
        pass
        pass
        user_id = int(state.split(":")[0])
    except Exception:
        pass
        return redirect("/dashboard?error=invalid_state")
    try:
        pass
        pass
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req) as r:
            tokens = json.loads(r.read())
    except urllib.error.HTTPError as e:
        pass
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[OAUTH] Token exchange HTTP error: {e.code} {e.reason}")
        print(f"[OAUTH] Google response body: {error_body}")
        print(f"[OAUTH] redirect_uri used: {REDIRECT_URI}")
        print(f"[OAUTH] client_id used: {CLIENT_ID}")
        return redirect("/dashboard?error=token_exchange_failed")
    except Exception as e:
        pass
        print(f"[OAUTH] Token exchange failed: {e}")
        print(f"[OAUTH] redirect_uri used: {REDIRECT_URI}")
        print(f"[OAUTH] client_id used: {CLIENT_ID}")
        return redirect("/dashboard?error=token_exchange_failed")
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    channel_name = "My Channel"
    yt_channel_id = ""
    sub_count = view_count = vid_count = 0
    profile_pic = ""
    try:
        pass
        pass
        yt_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true",
            headers={
                "Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(yt_req) as r:
            yt_data = json.loads(r.read())
        item = yt_data["items"][0]
        channel_name = item["snippet"]["title"]
        yt_channel_id = item["id"]
        profile_pic = item["snippet"].get(
            "thumbnails",
            {}).get(
            "default",
            {}).get(
            "url",
            "")
        stats = item.get("statistics", {})
        sub_count = int(stats.get("subscriberCount", 0))
        view_count = int(stats.get("viewCount", 0))
        vid_count = int(stats.get("videoCount", 0))
    except Exception as e:
        pass
        print(f"[OAUTH] YouTube channel fetch failed: {e}")
    db = get_db()
    existing = db.execute(
        "SELECT id FROM channels WHERE youtube_channel_id=? AND user_id=?",
        (yt_channel_id,
         user_id)).fetchone()
    if existing:
        pass
        db.execute(
            "UPDATE channels SET refresh_token=?, access_token=?, active=1, "
            "subscriber_count=?, view_count=?, video_count=?, profile_picture_url=? WHERE id=?",
            (refresh_token,
             access_token,
             sub_count,
             view_count,
             vid_count,
             profile_pic,
             existing["id"]))
    else:
        pass
        db.execute(
            "INSERT INTO channels (user_id, channel_name, youtube_channel_id, refresh_token, access_token, "
            "subscriber_count, view_count, video_count, profile_picture_url) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id,
             channel_name,
             yt_channel_id,
             refresh_token,
             access_token,
             sub_count,
             view_count,
             vid_count,
             profile_pic))
    db.commit()
    token = make_token(user_id)
    session["token"] = token
    return redirect("/dashboard?connected=1")

# ── Channel API ─────────────────────────────────────────────────────────


@app.route("/api/channels")
@login_required
def get_channels():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT id, channel_name, youtube_channel_id, niche, video_type, schedule, videos_uploaded, created_at "
        "FROM channels WHERE user_id=? AND active=1 ORDER BY created_at DESC", (request.uid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/channels/<int:cid>", methods=["PUT"])
@login_required
def update_channel(cid):
    pass
    d = request.get_json() or {}
    db = get_db()
    db.execute(
        "UPDATE channels SET niche=?, video_type=?, schedule=? WHERE id=? AND user_id=?",
        (d.get("niche"),
         d.get("video_type"),
         d.get("schedule"),
         cid,
         request.uid))
    db.commit()
    return jsonify({"status": "updated"})


@app.route("/api/channels/<int:cid>/sync", methods=["POST"])
@login_required
def sync_channel(cid):
    pass
    db = get_db()
    ch = db.execute("SELECT * FROM channels WHERE id=? AND user_id=?",
                    (cid, request.uid)).fetchone()
    if not ch:
        return jsonify({"error": "Channel not found"}), 404
    try:
        from worker import refresh_yt_token
        token = refresh_yt_token(ch["refresh_token"])
        yt_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true",
            headers={
                "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(yt_req) as r:
            yt_data = json.loads(r.read())
        item = yt_data["items"][0]
        stats = item.get("statistics", {})
        pic = item["snippet"].get(
            "thumbnails",
            {}).get(
            "default",
            {}).get(
            "url",
            "")
        db.execute(
            "UPDATE channels SET subscriber_count=?, view_count=?, video_count=?, profile_picture_url=? WHERE id=?", (int(
                stats.get(
                    "subscriberCount", 0)), int(
                stats.get(
                    "viewCount", 0)), int(
                        stats.get(
                            "videoCount", 0)), pic, cid))
        db.commit()
        return jsonify({"success": True, "subscriber_count": int(
            stats.get("subscriberCount", 0))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/channels/<int:cid>", methods=["DELETE"])
@login_required
def delete_channel(cid):
    pass
    db = get_db()
    db.execute(
        "UPDATE channels SET active=0 WHERE id=? AND user_id=?",
        (cid,
         request.uid))
    db.commit()
    return jsonify({"status": "deleted"})

# ── Video / Queue API ───────────────────────────────────────────────────


@app.route("/api/videos/generate", methods=["POST"])
@login_required
def generate_video():
    pass
    d = request.get_json() or {}
    channel_id = d.get("channel_id")
    # Multi-channel support: accept channel_ids array or single channel_id
    channel_ids = d.get("channel_ids", [])
    if channel_id and not channel_ids:
        channel_ids = [channel_id]
    if not channel_ids:
        return jsonify({"error": "channel_id or channel_ids required"}), 400
    niche = d.get("niche", "personal_finance")
    video_type = d.get("video_type", "short")
    custom_prompt = d.get("custom_prompt", "")
    custom_title = d.get("custom_title", "")
    db = get_db()
    # Verify channels
    valid_channels = []
    for cid in channel_ids:
        ch = db.execute("SELECT id FROM channels WHERE id=? AND user_id=?",
                        (cid, request.uid)).fetchone()
        if ch:
            valid_channels.append(cid)
    if not valid_channels:
        return jsonify({"error": "No valid channels found"}), 404
    # Server-side plan gating
    user_row = db.execute(
        "SELECT plan, COALESCE(trial_ends_at,0) AS trial_ends_at FROM users WHERE id=?",
        (request.uid,
         )).fetchone()
    plan_key = user_row["plan"] if user_row else "starter"
    trial_active = int(
        user_row["trial_ends_at"] or 0) > int(
        time.time()) if user_row else False
    effective_plan = "pro" if (
        trial_active and plan_key == "starter") else plan_key
    limits = PLANS.get(effective_plan, PLANS["starter"])
    if not limits.get("custom_prompts") and custom_prompt:
        pass
        return jsonify({"error": "Custom prompts require Pro plan"}), 403
    if limits["videos_per_week"] < 999:
        pass
        from datetime import datetime, timedelta
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        week_count = db.execute(
            "SELECT COUNT(*) FROM queue WHERE user_id=? AND created_at > ?",
            (request.uid, week_ago)
        ).fetchone()[0]
        if week_count >= limits["videos_per_week"]:
            pass
            return jsonify(
                {"error": f"Weekly limit of {limits['videos_per_week']} videos reached. Upgrade to generate more."}), 429
    # Queue one job per channel
    job_ids = []
    for cid in valid_channels:
        job_id = db.execute(
            "INSERT INTO queue (user_id, channel_id, video_type, niche, custom_prompt, custom_title) VALUES (?,?,?,?,?,?)",
            (request.uid, cid, video_type, niche, custom_prompt, custom_title)
        ).lastrowid
        job_ids.append(job_id)
        if celery_app:
            process_video_task.delay(job_id)
    db.commit()
    # Backwards compat: return single job_id if only one channel
    if len(job_ids) == 1:
        return jsonify({"success": True, "job_id": job_ids[0], "job_ids": job_ids,
                       "status": "queued", "queue": "celery" if celery_app else "sqlite"})
    return jsonify({"success": True, "job_ids": job_ids, "channels": len(job_ids),
                   "status": "queued", "queue": "celery" if celery_app else "sqlite"})


@app.route("/api/videos/generate-script", methods=["POST"])
@login_required
def generate_script_api():
    pass
    """Generate a video script without queuing a full job."""
    d = request.get_json() or {}
    prompt = d.get("prompt", "")
    niche = d.get("niche", "personal_finance")
    video_type = d.get("video_type", "short")
    if not prompt and not niche:
        pass
        return jsonify({"error": "Provide prompt or niche"}), 400
    script = generate_script(prompt, niche, video_type)
    return jsonify({
        "script": script,
        "provider": "openai" if (OPENAI_KEY and HAS_OPENAI) else "built-in",
        "niche": niche,
        "video_type": video_type,
    })


@app.route("/api/videos/queue")
@login_required
def get_queue():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT q.*, c.channel_name FROM queue q LEFT JOIN channels c ON q.channel_id=c.id "
        "WHERE q.user_id=? ORDER BY q.created_at DESC LIMIT 30", (request.uid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/videos/status/<int:job_id>")
@login_required
def job_status(job_id):
    pass
    db = get_db()
    job = db.execute("SELECT * FROM queue WHERE id=? AND user_id=?",
                     (job_id, request.uid)).fetchone()
    return jsonify(dict(job)) if job else (
        jsonify({"error": "Not found"}), 404)


@app.route("/api/videos")
@login_required
def get_videos():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT v.*, c.channel_name FROM videos v LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50", (request.uid,)).fetchall()
    return jsonify([dict(r) for r in rows])


ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max upload


@app.route("/api/videos/upload-own", methods=["POST"])
@login_required
def upload_own_video():
    """User uploads their own MP4/MOV/AVI/WEBM file for direct YouTube upload."""
    f = request.files.get("video")
    channel_ids_raw = request.form.get("channel_ids", "")
    channel_id = request.form.get("channel_id", "")
    custom_title = request.form.get("title", "").strip() or request.form.get("custom_title", "").strip()

    # Support single or multiple channels
    if channel_ids_raw:
        try:
            channel_ids = [int(x) for x in channel_ids_raw.split(",") if x.strip()]
        except Exception:
            channel_ids = []
    elif channel_id:
        try:
            channel_ids = [int(channel_id)]
        except Exception:
            channel_ids = []
    else:
        channel_ids = []

    if not f:
        return jsonify({"error": "No video file provided"}), 400
    if not channel_ids:
        return jsonify({"error": "channel_id or channel_ids required"}), 400

    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        return jsonify({"error": f"File type not allowed. Accepted: {', '.join(sorted(ALLOWED_VIDEO_EXTS))}"}), 400

    db = get_db()
    # Verify all channels belong to user
    for cid in channel_ids:
        ch = db.execute("SELECT id FROM channels WHERE id=? AND user_id=?", (cid, request.uid)).fetchone()
        if not ch:
            return jsonify({"error": f"Channel {cid} not found"}), 404

    # Save file once
    upload_dir = os.path.join(os.getcwd(), "uploads", "videos")
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"upload_{request.uid}_{int(time.time())}{ext}"
    fpath = os.path.join(upload_dir, fname)
    f.save(fpath)

    # Queue one job per channel
    job_ids = []
    for cid in channel_ids:
        job_id = db.execute(
            "INSERT INTO queue (user_id, channel_id, video_type, niche, custom_title, video_file_path, status) VALUES (?,?,?,?,?,?,'pending')",
            (request.uid, cid, "custom_upload", "personal_finance", custom_title, fpath)
        ).lastrowid
        job_ids.append(job_id)
    db.commit()

    return jsonify({
        "success": True,
        "job_ids": job_ids,
        "file": fname,
        "channels": len(channel_ids),
        "status": "queued",
        "message": f"Video queued for upload to {len(channel_ids)} channel(s)"
    })


@app.route("/uploads/videos/<path:filename>")
def serve_uploaded_videos(filename):
    upload_dir = os.path.join(os.getcwd(), "uploads", "videos")
    return send_from_directory(upload_dir, filename)

# ── Social API ──────────────────────────────────────────────────────────


@app.route("/api/social/<int:cid>")
@login_required
def get_social(cid):
    pass
    db = get_db()
    rows = db.execute(
        "SELECT id, platform, active FROM social_accounts WHERE channel_id=?",
        (cid,
         )).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/social/<int:cid>", methods=["POST"])
@login_required
def save_social(cid):
    pass
    d = request.get_json() or {}
    platform = d.get("platform")
    credentials = json.dumps(d.get("credentials", {}))
    db = get_db()
    ex = db.execute(
        "SELECT id FROM social_accounts WHERE channel_id=? AND platform=?",
        (cid,
         platform)).fetchone()
    if ex:
        pass
        db.execute(
            "UPDATE social_accounts SET credentials=?, active=1 WHERE id=?",
            (credentials,
             ex["id"]))
    else:
        pass
        db.execute(
            "INSERT INTO social_accounts (channel_id, platform, credentials) VALUES (?,?,?)",
            (cid,
             platform,
             credentials))
    db.commit()
    return jsonify({"status": "saved"})

# ── Prompts API ─────────────────────────────────────────────────────────


@app.route("/api/prompts", methods=["GET"])
@login_required
def get_prompts():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT * FROM prompts WHERE user_id=? ORDER BY created_at DESC",
        (request.uid,
         )).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/prompts", methods=["POST"])
@login_required
def create_prompt():
    pass
    d = request.get_json() or {}
    title = d.get("title", "").strip()
    body = d.get("body", "").strip()
    niche = d.get("niche", "personal_finance")
    if not title or not body:
        pass
        return jsonify({"error": "Title and body required"}), 400
    db = get_db()
    pid = db.execute(
        "INSERT INTO prompts (user_id, title, body, niche) VALUES (?,?,?,?)",
        (request.uid, title, body, niche)
    ).lastrowid
    db.commit()
    return jsonify({"success": True, "id": pid})


@app.route("/api/prompts/<int:pid>", methods=["DELETE"])
@login_required
def delete_prompt(pid):
    pass
    db = get_db()
    db.execute("DELETE FROM prompts WHERE id=? AND user_id=?",
               (pid, request.uid))
    db.commit()
    return jsonify({"success": True})

# ── Referral API ────────────────────────────────────────────────────────


@app.route("/api/referral/stats")
@login_required
def referral_stats():
    pass
    db = get_db()
    user = db.execute(
        "SELECT referral_code FROM users WHERE id=?",
        (request.uid,
         )).fetchone()
    count = db.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id=?",
        (request.uid,
         )).fetchone()[0]
    code = user["referral_code"] if user else ""
    tiers = [
        {"threshold": 1, "reward": "1 week Pro", "reached": count >= 1},
        {"threshold": 3, "reward": "1 month Pro", "reached": count >= 3},
        {"threshold": 10, "reward": "3 months Agency", "reached": count >= 10},
        {"threshold": 25, "reward": "Lifetime Pro", "reached": count >= 25},
    ]
    return jsonify({
        "referral_code": code,
        "referral_url": f"{APP_URL}/?ref={code}",
        "total_referrals": count,
        "tiers": tiers,
        "next_tier": next((t for t in tiers if not t["reached"]), None),
    })

# ── Promotions API ──────────────────────────────────────────────────────


@app.route("/api/promotions/submit", methods=["POST"])
@login_required
def submit_promotion():
    pass
    d = request.get_json() or {}
    tweet_url = d.get("tweet_url", "").strip()
    if not tweet_url or "twitter.com" not in tweet_url and "x.com" not in tweet_url:
        pass
        return jsonify({"error": "Valid tweet URL required"}), 400
    db = get_db()
    existing = db.execute(
        "SELECT id FROM promotions WHERE user_id=? AND status='pending'",
        (request.uid,
         )).fetchone()
    if existing:
        pass
        return jsonify(
            {"error": "You already have a pending promotion review"}), 400
    db.execute("INSERT INTO promotions (user_id, tweet_url) VALUES (?,?)",
               (request.uid, tweet_url))
    db.commit()
    return jsonify(
        {"success": True, "message": "Submitted! Admin will review within 48h."})

# ── Stats API ───────────────────────────────────────────────────────────


@app.route("/api/stats")
@login_required
def stats():
    pass
    db = get_db()
    channels = db.execute(
        "SELECT COUNT(*) FROM channels WHERE user_id=? AND active=1",
        (request.uid,
         )).fetchone()[0]
    uploaded = db.execute(
        "SELECT COUNT(*) FROM videos WHERE user_id=? AND status='uploaded'",
        (request.uid,
         )).fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM queue WHERE user_id=? AND status='pending'",
        (request.uid,
         )).fetchone()[0]
    processing = db.execute(
        "SELECT COUNT(*) FROM queue WHERE user_id=? AND status='processing'",
        (request.uid,
         )).fetchone()[0]
    user = db.execute("SELECT plan FROM users WHERE id=?",
                      (request.uid,)).fetchone()
    plan = user["plan"] if user else "starter"
    return jsonify({
        "channels": channels, "videos_uploaded": uploaded,
        "queue_pending": pending, "queue_processing": processing,
        "plan": plan, "plan_limits": PLANS.get(plan, PLANS["starter"]),
    })

# ── Payment API ─────────────────────────────────────────────────────────


@app.route("/api/payments/request", methods=["POST"])
@login_required
def payment_request():
    pass
    """User requests a plan upgrade — creates pending payment record."""
    d = request.get_json() or {}
    plan = d.get("plan", "")
    provider = d.get("provider") or d.get("payment_method", "manual")
    reference = d.get("reference", "")
    if plan not in PLANS or PLANS[plan]["price"] == 0:
        pass
        return jsonify({"error": "Invalid plan or plan is free"}), 400
    amount = PLANS[plan]["price"]
    db = get_db()
    db.execute(
        "UPDATE payments SET status='cancelled' WHERE user_id=? AND status='pending'",
        (request.uid,
         ))
    payment_id = db.execute(
        "INSERT INTO payments (user_id, amount, plan, provider, payment_method, reference, status) VALUES (?,?,?,?,?,?,'pending')",
        (request.uid, amount, plan, provider, provider, reference)
    ).lastrowid
    db.commit()
    if reference:
        pass
        db2 = get_db()
        db2.execute(
            "UPDATE payments SET status='submitted', reference=? WHERE id=?",
            (reference,
             payment_id))
        db2.commit()
        db2.close()
    resp = {
        "success": True,
        "payment_id": payment_id,
        "plan": plan,
        "amount": amount,
        "provider": provider,
        "status": "submitted" if reference else "pending",
        "message": "Payment request submitted. Admin will review within 24h." if reference else "Payment created.",
    }
    if provider == "stripe" and HAS_STRIPE and STRIPE_KEY:
        pass
        resp["instructions"] = "Use /api/payments/stripe-checkout to get a Stripe checkout URL"
    elif provider == "jazzcash":
        pass
        resp["instructions"] = f"Send PKR {amount * 280:.0f} to our JazzCash account and submit reference via /api/payments/manual"
    elif provider == "easypaisa":
        pass
        resp["instructions"] = f"Send PKR {amount * 280:.0f} to our EasyPaisa account and submit reference via /api/payments/manual"
    elif provider == "razorpay":
        pass
        resp["instructions"] = "Integrate with Razorpay order creation and submit reference via /api/payments/manual"
    else:
        pass
        resp["instructions"] = f"Transfer ${amount} via bank/wire and submit reference number via /api/payments/manual"
    return jsonify(resp)


@app.route("/api/payments/manual", methods=["POST"])
@login_required
def payment_manual():
    pass
    """User submits bank transfer / JazzCash / EasyPaisa reference number."""
    d = request.get_json() or {}
    reference = d.get("reference", "").strip()
    payment_id = d.get("payment_id")
    notes = d.get("notes", "")
    if not reference:
        pass
        return jsonify({"error": "Reference number required"}), 400
    db = get_db()
    payment = None
    if payment_id:
        pass
        payment = db.execute(
            "SELECT * FROM payments WHERE id=? AND user_id=? AND status='pending'",
            (payment_id, request.uid)
        ).fetchone()
    if not payment:
        pass
        payment = db.execute(
            "SELECT * FROM payments WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
            (request.uid,)
        ).fetchone()
    if not payment:
        pass
        return jsonify(
            {"error": "No pending payment found. Use /api/payments/request first"}), 404
    db.execute(
        "UPDATE payments SET reference=?, notes=?, status='submitted', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (reference, notes, payment["id"])
    )
    db.commit()
    admin = db.execute(
        "SELECT email FROM users WHERE is_admin=1 LIMIT 1").fetchone()
    user = db.execute(
        "SELECT email, full_name FROM users WHERE id=?",
        (request.uid,
         )).fetchone()
    if admin:
        pass
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
        "status": "submitted",
        "message": "Reference submitted. Admin will review within 24h.",
        "payment_id": payment["id"],
    })


@app.route("/api/payments/status")
@login_required
def payment_status():
    pass
    """User checks their payment history and status."""
    db = get_db()
    rows = db.execute(
        "SELECT id, amount, plan, provider, status, reference, created_at, updated_at "
        "FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
        (request.uid,)
    ).fetchall()
    return jsonify({"payments": [dict(r) for r in rows]})


@app.route("/api/payments/stripe-checkout", methods=["POST"])
@login_required
def stripe_checkout():
    pass
    """Create a Stripe Checkout Session for subscription."""
    if not HAS_STRIPE or not STRIPE_KEY:
        pass
        return jsonify(
            {"error": "Stripe not configured — set STRIPE_SECRET_KEY"}), 503
    d = request.get_json() or {}
    plan = d.get("plan", "pro")
    if plan not in PLANS or PLANS[plan]["price"] == 0:
        pass
        return jsonify({"error": "Invalid plan"}), 400
    try:
        pass
        pass
        sess = stripe_lib.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"FinanceFlow {PLANS[plan]['name']} Plan"},
                    "recurring": {"interval": "month"},
                    "unit_amount": PLANS[plan]["price"] * 100,
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
        pass
        return jsonify({"error": str(e)}), 500


@app.route("/api/payments/stripe-webhook", methods=["POST"])
def stripe_webhook():
    pass
    """Stripe webhook — verifies signature, upgrades/downgrades plan."""
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    event = None
    if HAS_STRIPE and STRIPE_WH_SECRET:
        pass
        try:
            pass
            pass
            event = stripe_lib.Webhook.construct_event(
                payload, sig, STRIPE_WH_SECRET)
        except stripe_lib.error.SignatureVerificationError:
            pass
            return jsonify({"error": "Invalid signature"}), 400
    else:
        pass
        try:
            pass
            pass
            event = json.loads(payload)
        except Exception:
            pass
            return jsonify({"error": "Invalid payload"}), 400
    etype = event.get("type", "")
    print(f"[STRIPE WEBHOOK] {etype}")
    if etype == "checkout.session.completed":
        pass
        sess = event["data"]["object"]
        user_id = int(sess.get("metadata", {}).get("user_id", 0))
        plan = sess.get("metadata", {}).get("plan", "pro")
        sub_id = sess.get("subscription", "")
        if user_id:
            pass
            db = get_db()
            db.execute(
                "UPDATE users SET plan=?, stripe_subscription_id=? WHERE id=?",
                (plan,
                 sub_id,
                 user_id))
            db.execute(
                "INSERT INTO payments (user_id, amount, plan, provider, status, reference) VALUES (?,?,?,'stripe','approved',?)",
                (user_id,
                 PLANS.get(
                     plan,
                     {}).get(
                     "price",
                     0),
                    plan,
                    sub_id))
            db.commit()
            user = db.execute(
                "SELECT email, full_name FROM users WHERE id=?", (user_id,)).fetchone()
            if user:
                pass
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
        pass
        sub_id = event["data"]["object"].get("id", "")
        if sub_id:
            pass
            db = get_db()
            db.execute(
                "UPDATE users SET plan='starter' WHERE stripe_subscription_id=?", (sub_id,))
    return jsonify({"status": "ok"})

# ── Admin payment API ───────────────────────────────────────────────────


@app.route("/api/admin/payments")
@admin_required
def admin_payments():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT p.*, u.email, u.full_name FROM payments p "
        "LEFT JOIN users u ON p.user_id=u.id "
        "ORDER BY p.created_at DESC LIMIT 100"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/payments/<int:pid>/approve", methods=["POST"])
@admin_required
def admin_approve_payment(pid):
    pass
    db = get_db()
    payment = db.execute(
        "SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not payment:
        pass
        return jsonify({"error": "Payment not found"}), 404
    db.execute(
        "UPDATE payments SET status='approved', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (pid,
         ))
    db.execute("UPDATE users SET plan=? WHERE id=?",
               (payment["plan"], payment["user_id"]))
    db.commit()
    user = db.execute(
        "SELECT email, full_name FROM users WHERE id=?",
        (payment["user_id"],
         )).fetchone()
    if user:
        pass
        send_email(
            user["email"],
            user["full_name"],
            f"✅ Payment approved — You're now on {payment['plan'].title()}!",
            f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#4F46E5">Payment Approved!</h2>
            <p>Your <b>{payment['plan'].title()}</b> plan is now active. Thank you!</p>
            <a href="{APP_URL}/dashboard" style="display:inline-block;background:#4F46E5;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold">
                Go to Dashboard →
            </a></div>""")
    return jsonify({"status": "approved",
                    "plan": payment["plan"],
                    "user_id": payment["user_id"]})


@app.route("/api/admin/payments/<int:pid>/reject", methods=["POST"])
@admin_required
def admin_reject_payment(pid):
    pass
    d = request.get_json() or {}
    reason = d.get("reason", "Payment could not be verified")
    db = get_db()
    payment = db.execute(
        "SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not payment:
        pass
        return jsonify({"error": "Payment not found"}), 404
    db.execute(
        "UPDATE payments SET status='rejected', notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (reason, pid)
    )
    db.commit()
    user = db.execute(
        "SELECT email, full_name FROM users WHERE id=?",
        (payment["user_id"],
         )).fetchone()
    if user:
        pass
        send_email(
            user["email"], user["full_name"],
            "Payment not approved — action required",
            f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
            <h2 style="color:#ef4444">Payment Not Approved</h2>
            <p>Reason: {reason}</p>
            <p>Please contact support or resubmit with the correct reference.</p></div>"""
        )
    return jsonify({"status": "rejected"})

# ── Admin API ───────────────────────────────────────────────────────────


@app.route("/api/admin/create", methods=["POST"])
def create_admin():
    pass
    d = request.get_json() or {}
    if d.get("master_key") != MASTER_KEY:
        pass
        return jsonify({"error": "Not authorized"}), 403
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (email, password_hash, is_admin) VALUES (?,?,1)",
            (email,
             hash_pw(password)))
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower() or isinstance(e, sqlite3.IntegrityError):
            db.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
        else:
            raise
    db.commit()
    return jsonify({"status": "admin created"})


@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    pass
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_vids = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    uploaded = db.execute(
        "SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0]
    total_chans = db.execute(
        "SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    pro = db.execute(
        "SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0]
    agency = db.execute(
        "SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0]
    growth = db.execute(
        "SELECT COUNT(*) FROM users WHERE plan='growth'").fetchone()[0]
    queue_pending = db.execute(
        "SELECT COUNT(*) FROM queue WHERE status IN ('pending','processing')").fetchone()[0]
    pending_pays = db.execute(
        "SELECT COUNT(*) FROM payments WHERE status IN ('pending','submitted')").fetchone()[0]
    return jsonify({
        "total_users": total_users,
        "total_videos": total_vids,
        "uploaded": uploaded,
        "total_channels": total_chans,
        "mrr": (pro * 29) + (agency * 99) + (growth * 49),
        "pro_users": pro,
        "agency_users": agency,
        "growth_users": growth,
        "queue_pending": queue_pending,
        "pending_payments": pending_pays,
        "worker_online": worker_online_status(),
    })


@app.route("/api/admin/users")
@admin_required
def admin_users():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT id, email, full_name, plan, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/users/<int:uid>/plan", methods=["PUT", "POST"])
@admin_required
def admin_set_plan(uid):
    pass
    d = request.get_json() or {}
    db = get_db()
    db.execute("UPDATE users SET plan=? WHERE id=?",
               (d.get("plan", "starter"), uid))
    db.commit()
    return jsonify({"status": "updated"})


@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    pass
    db = get_db()
    # Prevent deleting other admins
    target = db.execute(
        "SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
    if target and target["is_admin"]:
        pass
        return jsonify({"error": "Cannot delete admin accounts"}), 403
    # Cascade delete
    db.execute("DELETE FROM queue    WHERE user_id=?", (uid,))
    db.execute("DELETE FROM videos   WHERE user_id=?", (uid,))
    db.execute("UPDATE channels SET active=0 WHERE user_id=?", (uid,))
    db.execute("DELETE FROM payments WHERE user_id=?", (uid,))
    db.execute(
        "DELETE FROM referrals WHERE referrer_id=? OR referred_id=?", (uid, uid))
    db.execute("DELETE FROM email_sequences WHERE user_id=?", (uid,))
    db.execute("DELETE FROM promotions WHERE user_id=?", (uid,))
    db.execute("DELETE FROM users    WHERE id=?", (uid,))
    db.commit()
    return jsonify({"status": "deleted"})


@app.route("/api/admin/channels")
@admin_required
def admin_channels():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT c.*, u.email FROM channels c LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.active=1 ORDER BY c.created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/videos")
@admin_required
def admin_videos():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT v.*, u.email, c.channel_name FROM videos v "
        "LEFT JOIN users u ON v.user_id=u.id "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "ORDER BY v.created_at DESC LIMIT 100"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/social-keys", methods=["POST"])
@admin_required
def admin_save_social_keys():
    pass
    d = request.get_json() or {}
    platform = d.get("platform", "")
    creds = d.get("creds", {})
    try:
        pass
        pass
        db = get_db()
        sk_row = db.execute(
            "SELECT value FROM system_settings WHERE key='social_keys'").fetchone()
        existing = json.loads(
            sk_row["value"]) if sk_row and sk_row["value"] else {}
        existing[platform] = creds
        val = json.dumps(existing)
        if sk_row:
            db.execute(
                "UPDATE system_settings SET value=? WHERE key='social_keys'", (val,))
        else:
            db.execute(
                "INSERT INTO system_settings (key, value) VALUES ('social_keys',?)", (val,))
        db.commit()
        return jsonify({"status": "saved"})
    except Exception as e:
        pass
        return jsonify({"error": str(e)}), 500

# ── Reddit templates + System channel ──────────────────────────────────

REDDIT_TEMPLATES = [
    {
        "subreddit": "r/passive_income",
        "title": "I automated my YouTube channel completely — here's how it generates income while I sleep",
        "body": "Been using an AI tool called FinanceFlow for the past few months and wanted to share the results.\n\nThe system automatically:\n- Generates short-form finance/investing content\n- Uploads to YouTube on a schedule\n- Handles all the SEO metadata\n\nI went from 0 to [X] subscribers without recording a single video myself. The channel covers [niche] and monetization kicked in at 1,000 subs.\n\nHappy to answer questions about the setup. The tool is at [your Railway URL]\n\n**Edit:** For those asking — no, I'm not affiliated, just a user sharing results."
    },
    {
        "subreddit": "r/SaaS",
        "title": "Built a YouTube automation SaaS — here's what I learned shipping it",
        "body": "Just launched FinanceFlow, a tool that auto-generates and uploads YouTube Shorts for finance creators.\n\n**The stack:**\n- Python/Flask backend\n- ffmpeg + moviepy for video rendering\n- YouTube Data API v3 for uploads\n- Railway for hosting\n\n**What surprised me:**\n1. Memory management on cheap VPS is the hardest part (ffmpeg loves RAM)\n2. YouTube's OAuth refresh flow breaks in weird ways in production\n3. Users want autopilot more than customization\n\nMRR is early but growing. Happy to share learnings or answer questions.\n\nSite: [your Railway URL]"
    },
    {
        "subreddit": "r/youtubers",
        "title": "How I'm posting daily finance Shorts without filming anything",
        "body": "Quick breakdown of my current setup for anyone curious about faceless YouTube:\n\n**Niche:** Personal finance / investing tips\n**Format:** 60-second Shorts with text overlays\n**Posting schedule:** 1-2 per day, fully automated\n\nI use FinanceFlow ([your Railway URL]) which handles script → voiceover → video → upload automatically.\n\n**Results after 90 days:**\n- [X] subscribers\n- [Y] total views\n- Monetization: [status]\n\nThe key insight: consistency beats quality at the Shorts stage. Daily posting compounds.\n\nAMA about the setup."
    },
    {
        "subreddit": "r/EntrepreneurRideAlong",
        "title": "Month [X] update: building a YouTube automation SaaS in public",
        "body": "**FinanceFlow — Monthly Update**\n\n**What it does:** Automatically generates and uploads finance YouTube Shorts using AI\n\n**This month's numbers:**\n- Users: [X]\n- MRR: $[Y]\n- Videos generated: [Z]\n- Channels on autopilot: [N]\n\n**What worked:**\n- [specific growth tactic]\n- [feature that users loved]\n\n**What didn't:**\n- [honest failure]\n\n**Next month focus:**\n- [goal 1]\n- [goal 2]\n\nBuilding in public thread — ask me anything.\n\nProduct: [your Railway URL]"
    }
]


@app.route("/api/admin/reddit-templates")
@admin_required
def get_reddit_templates():
    return jsonify(REDDIT_TEMPLATES)


@app.route("/api/admin/system-channel", methods=["POST"])
@admin_required
def set_system_channel():
    data = request.get_json() or {}
    channel_id = data.get("channel_id", "").strip()
    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM system_settings WHERE key='system_channel_id'").fetchone()
        if existing:
            db.execute(
                "UPDATE system_settings SET value=? WHERE key='system_channel_id'", (channel_id,))
        else:
            db.execute(
                "INSERT INTO system_settings (key, value) VALUES ('system_channel_id',?)", (channel_id,))
        db.commit()
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Static file serving ─────────────────────────────────────────────────


@app.route("/uploads/<path:filename>")
def serve_uploads(filename):
    pass
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    return send_from_directory(uploads_dir, filename)


@app.route("/generated_videos/<path:filename>")
def serve_generated(filename):
    pass
    gen_dir = os.path.join(os.getcwd(), "generated_videos")
    return send_from_directory(gen_dir, filename)

# ── Queue status / cancel ───────────────────────────────────────────────


@app.route("/api/queue/status")
@login_required
def queue_status():
    pass
    db = get_db()
    q_rows = db.execute(
        "SELECT q.*, c.channel_name FROM queue q LEFT JOIN channels c ON q.channel_id=c.id "
        "WHERE q.user_id=? ORDER BY q.created_at DESC LIMIT 30", (request.uid,)).fetchall()
    v_rows = db.execute(
        "SELECT v.*, c.channel_name FROM videos v LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 50", (request.uid,)).fetchall()
    total = db.execute(
        "SELECT COUNT(*) FROM videos WHERE user_id=?",
        (request.uid,
         )).fetchone()[0]
    uploaded = db.execute(
        "SELECT COUNT(*) FROM videos WHERE user_id=? AND status='uploaded'",
        (request.uid,
         )).fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM queue WHERE user_id=? AND status='pending'",
        (request.uid,
         )).fetchone()[0]
    return jsonify({
        "queue": [dict(r) for r in q_rows],
        "videos": [dict(r) for r in v_rows],
        "stats": {"total": total, "uploaded": uploaded, "pending": pending},
        "worker_online": worker_online_status(),
    })


@app.route("/api/queue/<int:jid>/cancel", methods=["POST"])
@login_required
def cancel_job(jid):
    pass
    db = get_db()
    db.execute(
        "UPDATE queue SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'",
        (jid,
         request.uid))
    db.commit()
    return jsonify({"success": True})

# ── Channel settings / social / autopilot / monetized ────────────────────────


@app.route("/api/channels/<int:cid>/settings", methods=["POST"])
@login_required
def channel_settings(cid):
    pass
    d = request.get_json() or {}
    db = get_db()
    ch = db.execute(
        "SELECT id FROM channels WHERE id=? AND user_id=?",
        (cid,
         request.uid)).fetchone()
    if not ch:
        return jsonify({"error": "Channel not found"}), 404
    db.execute(
        "UPDATE channels SET niche=?, video_type=?, schedule=? WHERE id=? AND user_id=?",
        (d.get("niche"),
         d.get("voice_style"),
         d.get("upload_schedule"),
         cid,
         request.uid))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/channels/<int:cid>/social", methods=["GET"])
@login_required
def get_channel_social(cid):
    pass
    db = get_db()
    rows = db.execute(
        "SELECT platform, active FROM social_accounts WHERE channel_id=? AND active=1",
        (cid,
         )).fetchall()
    return jsonify({r["platform"]: {"active": r["active"]} for r in rows})


@app.route("/api/channels/<int:cid>/social", methods=["POST"])
@login_required
def save_channel_social(cid):
    pass
    d = request.get_json() or {}
    platform = d.get("platform")
    credentials = json.dumps(d.get("credentials", {}))
    db = get_db()
    ex = db.execute(
        "SELECT id FROM social_accounts WHERE channel_id=? AND platform=?",
        (cid,
         platform)).fetchone()
    if ex:
        pass
        db.execute(
            "UPDATE social_accounts SET credentials=?, active=1 WHERE id=?",
            (credentials,
             ex["id"]))
    else:
        pass
        db.execute(
            "INSERT INTO social_accounts (channel_id, platform, credentials) VALUES (?,?,?)",
            (cid,
             platform,
             credentials))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/channels/<int:cid>/social/<platform>", methods=["DELETE"])
@login_required
def delete_channel_social(cid, platform):
    pass
    db = get_db()
    db.execute(
        "UPDATE social_accounts SET active=0 WHERE channel_id=? AND platform=?",
        (cid,
         platform))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/channels/<int:cid>/autopilot", methods=["POST"])
@login_required
def toggle_autopilot(cid):
    pass
    d = request.get_json() or {}
    enabled = 1 if d.get("enabled") else 0
    db = get_db()
    db.execute("UPDATE channels SET autopilot=? WHERE id=? AND user_id=?",
               (enabled, cid, request.uid))
    db.commit()
    return jsonify({"success": True, "autopilot": bool(enabled)})


@app.route("/api/channels/<int:cid>/monetized", methods=["POST"])
@login_required
def mark_monetized(cid):
    pass
    d = request.get_json() or {}
    monetized = 1 if d.get("monetized") else 0
    db = get_db()
    db.execute("UPDATE channels SET monetized=? WHERE id=? AND user_id=?",
               (monetized, cid, request.uid))
    db.commit()
    return jsonify({"success": True})

# ── Account: password / branding / uploads / voice clone ─────────────────────


@app.route("/api/account/password", methods=["POST"])
@login_required
def change_password():
    pass
    d = request.get_json() or {}
    cur = d.get("current", "")
    new_pw = d.get("new", "")
    if not new_pw or len(new_pw) < 6:
        pass
        return jsonify({"error": "New password must be 6+ characters"}), 400
    db = get_db()
    u_row = db.execute(
        "SELECT id, password_hash FROM users WHERE id=?",
        (request.uid,
         )).fetchone()
    u = u_row if u_row and check_pw(cur, u_row["password_hash"]) else None
    if not u:
        return jsonify({"error": "Current password is incorrect"}), 401
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (hash_pw(new_pw), request.uid))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/account/branding", methods=["GET"])
@login_required
def get_branding():
    pass
    db = get_db()
    u = db.execute(
        "SELECT brand_color_primary, brand_color_accent, avatar_path, logo_path, custom_voice_id "
        "FROM users WHERE id=?", (request.uid,)).fetchone()
    return jsonify(dict(u)) if u else (jsonify({"error": "Not found"}), 404)


@app.route("/api/account/branding", methods=["POST"])
@login_required
def save_branding():
    pass
    d = request.get_json() or {}
    db = get_db()
    db.execute(
        "UPDATE users SET brand_color_primary=?, brand_color_accent=? WHERE id=?", (d.get(
            "brand_color_primary", "#FFD700"), d.get(
            "brand_color_accent", "#FFA500"), request.uid))
    db.commit()
    return jsonify({"success": True})


ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _upload_file(ftype):
    pass
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file"}), 400
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        pass
        return jsonify(
            {"error": f"File type not allowed. Use: {', '.join(ALLOWED_IMAGE_EXTS)}"}), 400
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    fname = f"{ftype}_{request.uid}{ext}"
    f.save(os.path.join(uploads_dir, fname))
    url = f"/uploads/{fname}"
    db = get_db()
    col = "avatar_path" if ftype == "avatar" else "logo_path"
    db.execute(f"UPDATE users SET {col}=? WHERE id=?", (url, request.uid))
    db.commit()
    return jsonify({"success": True, "url": url})


@app.route("/api/account/upload-avatar", methods=["POST"])
@login_required
def upload_avatar():
    pass
    return _upload_file("avatar")


@app.route("/api/account/upload-logo", methods=["POST"])
@login_required
def upload_logo():
    pass
    return _upload_file("logo")


@app.route("/api/account/onboarding-complete", methods=["POST"])
@login_required
def onboarding_complete():
    pass
    d = request.get_json() or {}
    db = get_db()
    db.execute(
        "UPDATE users SET onboarding_complete=1 WHERE id=?", (request.uid,))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/account/clone-voice", methods=["POST"])
@login_required
def clone_voice():
    pass
    if not ELEVENLABS_KEY:
        pass
        return jsonify(
            {"error": "ElevenLabs not configured — set ELEVENLABS_API_KEY"}), 503
    f = request.files.get("audio")
    name = request.form.get("name", f"User {request.uid} Voice")
    if not f:
        return jsonify({"error": "No audio file provided"}), 400
    try:
        pass
        pass
        boundary = b"----FormBoundary" + secrets.token_hex(8).encode()
        body = b"".join([
            b"--" + boundary + b"\r\n",
            b'Content-Disposition: form-data; name="name"\r\n\r\n',
            name.encode() + b"\r\n",
            b"--" + boundary + b"\r\n",
            b'Content-Disposition: form-data; name="files"; filename="voice.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n',
            f.read() + b"\r\n",
            b"--" + boundary + b"--\r\n",
        ])
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/voices/add",
            data=body,
            headers={
                "xi-api-key": ELEVENLABS_KEY,
                "Content-Type": f"multipart/form-data; boundary={boundary.decode()}"})
        with urllib.request.urlopen(req) as r:
            voice_id = json.loads(r.read()).get("voice_id", "")
        db = get_db()
        db.execute("UPDATE users SET custom_voice_id=? WHERE id=?",
                   (voice_id, request.uid))
        db.commit()
        return jsonify({"success": True, "voice_id": voice_id})
    except Exception as e:
        pass
        return jsonify({"error": str(e)}), 500

# ── Admin create-admin / channel toggles ─────────────────────────────────────


@app.route("/api/admin/create-admin", methods=["POST"])
@admin_required
def admin_create_admin():
    pass
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    name = d.get("name", "")
    password = d.get("password", "")
    if not email or not password:
        pass
        return jsonify({"error": "Email and password required"}), 400
    db = get_db()
    try:
        pass
        pass
        db.execute(
            "INSERT INTO users (email, password_hash, full_name, plan, is_admin) VALUES (?,?,?,'admin',1)",
            (email, hash_pw(password), name)
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower() or isinstance(e, sqlite3.IntegrityError):
            db.execute(
                "UPDATE users SET is_admin=1, plan='admin' WHERE email=?", (email,))
        else:
            raise
    db.commit()
    return jsonify({"success": True, "message": f"Admin {email} created"})


@app.route("/api/admin/channels/<int:cid>/autopilot", methods=["POST"])
@admin_required
def admin_toggle_autopilot(cid):
    pass
    d = request.get_json() or {}
    enabled = 1 if d.get("enabled") else 0
    db = get_db()
    db.execute("UPDATE channels SET autopilot=? WHERE id=?", (enabled, cid))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/admin/channels/<int:cid>/monetized", methods=["POST"])
@admin_required
def admin_mark_monetized(cid):
    pass
    d = request.get_json() or {}
    monetized = 1 if d.get("monetized") else 0
    db = get_db()
    db.execute("UPDATE channels SET monetized=? WHERE id=?", (monetized, cid))
    db.commit()
    return jsonify({"success": True})

# ── Admin promotions ────────────────────────────────────────────────────


@app.route("/api/admin/promotions")
@admin_required
def admin_promotions():
    pass
    db = get_db()
    rows = db.execute(
        "SELECT p.*, u.email FROM promotions p LEFT JOIN users u ON p.user_id=u.id "
        "ORDER BY p.created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/promotions/<int:pid>/approve", methods=["POST"])
@admin_required
def approve_promotion(pid):
    pass
    db = get_db()
    promo = db.execute(
        "SELECT * FROM promotions WHERE id=?", (pid,)).fetchone()
    if not promo:
        return jsonify({"error": "Promotion not found"}), 404
    db.execute("UPDATE promotions SET status='approved', channel_granted=1, "
               "reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
    # Grant extra channel slot by upgrading plan (simplified: just mark as
    # done)
    user = db.execute("SELECT email, full_name FROM users WHERE id=?",
                      (promo["user_id"],)).fetchone()
    if user:
        pass
        send_email(user["email"], user["full_name"],
                   "🎉 Free channel approved!",
                   f"""<div style="font-family:sans-serif">
                   <h2>Your free channel slot is approved!</h2>
                   <p>Thanks for spreading the word about FinanceFlow.</p>
                   <a href="{APP_URL}/dashboard">Go to Dashboard →</a></div>""")
    db.commit()
    return jsonify({"success": True})


@app.route("/api/admin/promotions/<int:pid>/reject", methods=["POST"])
@admin_required
def reject_promotion(pid):
    pass
    db = get_db()
    db.execute(
        "UPDATE promotions SET status='rejected', reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
        (pid,
         ))
    db.commit()
    return jsonify({"success": True})

# ── Admin system settings ───────────────────────────────────────────────


@app.route("/api/admin/settings", methods=["GET"])
@admin_required
def admin_get_settings():
    pass
    db = get_db()
    rows = db.execute("SELECT key, value FROM system_settings").fetchall()
    return jsonify({r["key"]: r["value"] for r in rows})


@app.route("/api/admin/settings", methods=["POST"])
@admin_required
def admin_save_settings():
    pass
    d = request.get_json() or {}
    db = get_db()
    for k, v in d.items():
        pass
        existing = db.execute(
            "SELECT key FROM system_settings WHERE key=?", (k,)).fetchone()
        if existing:
            pass
            db.execute(
                "UPDATE system_settings SET value=? WHERE key=?", (str(v), k))
        else:
            pass
            db.execute(
                "INSERT INTO system_settings (key, value) VALUES (?,?)", (k, str(v)))
    db.commit()
    return jsonify({"success": True})

# ── Health ──────────────────────────────────────────────────────────────


@app.route("/health")
def health():
    pass
    return jsonify({
        "status": "ok",
        "service": "FinanceFlow SaaS",
        "jwt": HAS_JWT,
        "openai": bool(OPENAI_KEY and HAS_OPENAI),
        "stripe": bool(STRIPE_KEY and HAS_STRIPE),
        "celery": bool(celery_app),
        "queue": "celery+redis" if celery_app else "sqlite",
    })


@app.route("/demo")
def demo():
    return render_template("demo.html")


@app.route("/api/mobile/docs")
def mobile_docs():
    docs_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FinanceFlow Mobile API Docs</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#050810;color:#e8eaf0;line-height:1.7}}
nav{{display:flex;align-items:center;justify-content:space-between;padding:16px 40px;background:rgba(5,8,16,0.97);border-bottom:1px solid #1f2937;position:sticky;top:0;z-index:10}}
.logo{{font-weight:800;font-size:20px;color:#FFD700;text-decoration:none}}
.container{{max-width:900px;margin:0 auto;padding:40px 24px 80px}}
h1{{font-size:36px;font-weight:800;color:#FFD700;margin-bottom:8px}}
.subtitle{{color:#6b7280;margin-bottom:40px}}
h2{{font-size:20px;font-weight:700;color:#e8eaf0;margin:40px 0 12px;padding-top:12px;border-top:1px solid #1f2937}}
h2:first-of-type{{border-top:none;margin-top:0}}
.endpoint{{background:#0a0f1e;border:1px solid #1f2937;border-radius:12px;padding:20px 24px;margin-bottom:20px}}
.method{{display:inline-block;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;margin-right:10px}}
.get{{background:rgba(34,197,94,0.15);color:#4ade80;border:1px solid rgba(34,197,94,0.3)}}
.post{{background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3)}}
.path{{font-family:monospace;font-size:15px;color:#e8eaf0}}
.desc{{color:#9ca3af;font-size:14px;margin-top:8px}}
.params{{margin-top:14px}}
.params h4{{font-size:13px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:6px 10px;color:#6b7280;font-weight:600;border-bottom:1px solid #1f2937}}
td{{padding:7px 10px;color:#9ca3af;border-bottom:1px solid rgba(31,41,55,0.5)}}
td:first-child{{font-family:monospace;color:#a5b4fc}}
code{{background:#0d1117;border:1px solid #1f2937;border-radius:6px;padding:12px 16px;display:block;font-family:monospace;font-size:13px;color:#9ca3af;margin-top:10px;white-space:pre;overflow-x:auto}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:rgba(255,215,0,0.1);color:#FFD700;border:1px solid rgba(255,215,0,0.2);margin-left:6px}}
footer{{border-top:1px solid #1f2937;padding:24px;text-align:center;color:#4b5563;font-size:13px}}
</style>
</head>
<body>
<nav><a href="/" class="logo">FinanceFlow</a><a href="/dashboard" style="color:#6b7280;font-size:14px;text-decoration:none">Dashboard →</a></nav>
<div class="container">
<h1>Mobile API Reference</h1>
<p class="subtitle">REST API for the FinanceFlow Android / iOS app &nbsp;·&nbsp; Base URL: <code style="display:inline;background:none;border:none;padding:0;color:#FFD700">{APP_URL}/api/mobile</code></p>

<h2>Authentication</h2>
<p style="color:#9ca3af;font-size:14px;margin-bottom:14px">Two methods are supported on every protected endpoint:</p>
<div class="endpoint">
<span class="badge">Option 1</span> <span style="color:#e8eaf0;font-size:14px">Bearer JWT token in <code style="display:inline;background:none;border:none;padding:0;color:#a5b4fc">Authorization</code> header</span>
<code>Authorization: Bearer &lt;token&gt;</code>
</div>
<div class="endpoint">
<span class="badge">Option 2</span> <span style="color:#e8eaf0;font-size:14px">API Key in <code style="display:inline;background:none;border:none;padding:0;color:#a5b4fc">X-API-Key</code> header</span>
<code>X-API-Key: &lt;your_api_key&gt;</code>
<p class="desc" style="margin-top:8px">Your API key is shown in Dashboard → Settings. It is the MD5 of <code style="display:inline;background:none;border:none;padding:0;font-size:12px">ff-&lt;user_id&gt;</code>.</p>
</div>

<h2>Endpoints</h2>

<div class="endpoint">
<span class="method post">POST</span><span class="path">/api/mobile/register</span>
<p class="desc">Create a new account.</p>
<div class="params"><h4>Request Body (JSON)</h4>
<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
<tbody>
<tr><td>full_name</td><td>string</td><td>yes</td><td>User's full name</td></tr>
<tr><td>email</td><td>string</td><td>yes</td><td>Email address</td></tr>
<tr><td>password</td><td>string</td><td>yes</td><td>Min 6 characters</td></tr>
</tbody></table></div>
<code>{{"token": "...", "user_id": 42, "name": "Jane Doe", "plan": "trial", "api_key": "abc123..."}}</code>
</div>

<div class="endpoint">
<span class="method post">POST</span><span class="path">/api/mobile/login</span>
<p class="desc">Log in and receive a JWT token + API key.</p>
<div class="params"><h4>Request Body (JSON)</h4>
<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
<tbody>
<tr><td>email</td><td>string</td><td>yes</td><td>Registered email</td></tr>
<tr><td>password</td><td>string</td><td>yes</td><td>Account password</td></tr>
</tbody></table></div>
<code>{{"token": "...", "user_id": 42, "name": "Jane Doe", "plan": "pro", "api_key": "abc123..."}}</code>
</div>

<div class="endpoint">
<span class="method get">GET</span><span class="path">/api/mobile/dashboard</span> <span class="badge">Auth required</span>
<p class="desc">Get the user's dashboard summary.</p>
<code>{{"user": {{"name": "...", "email": "...", "plan": "pro"}}, "channels": [{{"id": 1, "channel_name": "..."}}], "recent_jobs": [...], "stats": {{"total_videos": 12, "pending": 1}}}}</code>
</div>

<div class="endpoint">
<span class="method post">POST</span><span class="path">/api/mobile/generate</span> <span class="badge">Auth required</span>
<p class="desc">Generate and upload a video to YouTube.</p>
<div class="params"><h4>Request Body (JSON)</h4>
<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
<tbody>
<tr><td>channel_id</td><td>integer</td><td>yes</td><td>Channel ID from dashboard</td></tr>
<tr><td>video_type</td><td>string</td><td>no</td><td><code style="display:inline;background:none;border:none;padding:0">short</code> or <code style="display:inline;background:none;border:none;padding:0">long</code> (default: short)</td></tr>
<tr><td>custom_prompt</td><td>string</td><td>no</td><td>Custom script prompt</td></tr>
<tr><td>custom_title</td><td>string</td><td>no</td><td>Custom video title</td></tr>
</tbody></table></div>
<code>{{"success": true, "job_id": 99, "message": "Video queued"}}</code>
</div>

<div class="endpoint">
<span class="method post">POST</span><span class="path">/api/mobile/upload</span> <span class="badge">Auth required</span>
<p class="desc">Upload a video file directly to YouTube. Send as multipart/form-data.</p>
<div class="params"><h4>Form Fields</h4>
<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
<tbody>
<tr><td>video</td><td>file</td><td>yes</td><td>Video file (mp4, mov, avi, webm — max 2GB)</td></tr>
<tr><td>channel_id</td><td>integer</td><td>yes</td><td>Target channel ID</td></tr>
<tr><td>title</td><td>string</td><td>no</td><td>Custom video title</td></tr>
</tbody></table></div>
<code>{{"success": true, "job_id": 100}}</code>
</div>

<div class="endpoint">
<span class="method get">GET</span><span class="path">/api/mobile/videos</span> <span class="badge">Auth required</span>
<p class="desc">List recent video jobs (last 20).</p>
<code>[{{"id": 99, "title": "...", "status": "done", "yt_url": "https://youtu.be/...", "created_at": "..."}}]</code>
</div>

<h2>Error Responses</h2>
<p style="color:#9ca3af;font-size:14px;margin-bottom:14px">All errors return JSON with an <code style="display:inline;background:none;border:none;padding:0;color:#a5b4fc">error</code> key:</p>
<code>{{"error": "Unauthorized"}}  // 401
{{"error": "No channels connected"}}  // 400
{{"error": "Plan expired"}}  // 403</code>

</div>
<footer>© 2026 FinanceFlow &nbsp;·&nbsp; <a href="/privacy" style="color:#6b7280;text-decoration:none">Privacy</a> &nbsp;·&nbsp; <a href="/terms" style="color:#6b7280;text-decoration:none">Terms</a></footer>
</body>
</html>"""
    return docs_html


# ── CORS for mobile apps ─────────────────────────────────────────────────


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if ALLOWED_ORIGINS == "*":
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif origin and origin in ALLOWED_ORIGINS.split(","):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    else:
        response.headers["Access-Control-Allow-Origin"] = APP_URL
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    return response


@app.route("/api/mobile/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/api/mobile/<path:path>", methods=["OPTIONS"])
def mobile_preflight(path):
    from flask import Response
    return Response("", status=200)


# ── Mobile API helpers ───────────────────────────────────────────────────


def get_mobile_user():
    """Authenticate mobile requests via JWT Bearer token or X-API-Key."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        user = parse_token(auth[7:])
        if user:
            return user["user_id"]
    api_key = request.headers.get("X-API-Key", "") or request.args.get("api_key", "")
    if api_key:
        db = get_db()
        users = db.execute("SELECT id FROM users LIMIT 1000").fetchall()
        for u in users:
            if hashlib.md5(f"ff-{u['id']}".encode()).hexdigest() == api_key:
                return u["id"]
    return None


def mobile_login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        uid = get_mobile_user()
        if not uid:
            return jsonify({"error": "Unauthorized — provide Bearer token or X-API-Key"}), 401
        request.uid = uid
        return f(*a, **kw)
    return wrap


# ── Mobile API endpoints ──────────────────────────────────────────────────


@app.route("/api/mobile/dashboard")
@mobile_login_required
def mobile_dashboard():
    """GET /api/mobile/dashboard — full stats for mobile app."""
    db = get_db()
    u = db.execute(
        "SELECT id, email, full_name, plan, COALESCE(trial_ends_at,0) AS trial_ends_at, "
        "COALESCE(referral_code,'') AS referral_code FROM users WHERE id=?",
        (request.uid,)).fetchone()
    if not u:
        return jsonify({"error": "User not found"}), 404
    channels = db.execute(
        "SELECT id, channel_name, niche, video_type, COALESCE(subscriber_count,0) AS subscribers, "
        "COALESCE(view_count,0) AS views, videos_uploaded, COALESCE(autopilot,0) AS autopilot "
        "FROM channels WHERE user_id=? AND active=1", (request.uid,)).fetchall()
    total_videos = db.execute("SELECT COUNT(*) FROM videos WHERE user_id=?", (request.uid,)).fetchone()[0]
    uploaded = db.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND status='uploaded'", (request.uid,)).fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM queue WHERE user_id=? AND status IN ('pending','processing')", (request.uid,)).fetchone()[0]
    trial_active = int(u["trial_ends_at"] or 0) > int(time.time())
    api_key = hashlib.md5(f"ff-{u['id']}".encode()).hexdigest()
    return jsonify({
        "user": {
            "id": u["id"],
            "email": u["email"],
            "name": u["full_name"] or u["email"],
            "plan": u["plan"],
            "api_key": api_key,
            "trial_active": trial_active,
            "referral_code": u["referral_code"],
        },
        "stats": {
            "total_videos": total_videos,
            "uploaded": uploaded,
            "pending": pending,
            "channels": len(channels),
        },
        "channels": [dict(c) for c in channels],
        "worker_online": worker_online_status(),
    })


@app.route("/api/mobile/generate", methods=["POST"])
@mobile_login_required
def mobile_generate():
    """POST /api/mobile/generate — queue a video generation job."""
    d = request.get_json() or {}
    channel_id = d.get("channel_id")
    channel_ids = d.get("channel_ids", [])
    if channel_id and not channel_ids:
        channel_ids = [channel_id]
    if not channel_ids:
        return jsonify({"error": "channel_id required"}), 400
    niche = d.get("niche", "personal_finance")
    video_type = d.get("video_type", "short")
    custom_prompt = d.get("custom_prompt", "")
    custom_title = d.get("custom_title", "")
    db = get_db()
    job_ids = []
    for cid in channel_ids:
        ch = db.execute("SELECT id FROM channels WHERE id=? AND user_id=?", (cid, request.uid)).fetchone()
        if not ch:
            continue
        job_id = db.execute(
            "INSERT INTO queue (user_id, channel_id, video_type, niche, custom_prompt, custom_title) VALUES (?,?,?,?,?,?)",
            (request.uid, cid, video_type, niche, custom_prompt, custom_title)
        ).lastrowid
        job_ids.append(job_id)
    db.commit()
    if not job_ids:
        return jsonify({"error": "No valid channels"}), 404
    return jsonify({"success": True, "job_ids": job_ids, "status": "queued"})


@app.route("/api/mobile/upload", methods=["POST"])
@mobile_login_required
def mobile_upload():
    """POST /api/mobile/upload — upload own video file for a channel."""
    f = request.files.get("video")
    channel_id = request.form.get("channel_id", "")
    custom_title = request.form.get("title", "").strip()
    if not f or not channel_id:
        return jsonify({"error": "video file and channel_id required"}), 400
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        return jsonify({"error": f"File type not allowed. Use: {', '.join(sorted(ALLOWED_VIDEO_EXTS))}"}), 400
    db = get_db()
    try:
        cid = int(channel_id)
    except Exception:
        return jsonify({"error": "Invalid channel_id"}), 400
    ch = db.execute("SELECT id FROM channels WHERE id=? AND user_id=?", (cid, request.uid)).fetchone()
    if not ch:
        return jsonify({"error": "Channel not found"}), 404
    upload_dir = os.path.join(os.getcwd(), "uploads", "videos")
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"mobile_{request.uid}_{int(time.time())}{ext}"
    fpath = os.path.join(upload_dir, fname)
    f.save(fpath)
    job_id = db.execute(
        "INSERT INTO queue (user_id, channel_id, video_type, niche, custom_title, video_file_path, status) VALUES (?,?,?,?,?,?,'pending')",
        (request.uid, cid, "custom_upload", "personal_finance", custom_title, fpath)
    ).lastrowid
    db.commit()
    return jsonify({"success": True, "job_id": job_id, "status": "queued"})


@app.route("/api/mobile/upload-video", methods=["POST"])
@mobile_login_required
def mobile_upload_video():
    """POST /api/mobile/upload-video — alias of /api/mobile/upload for mobile apps."""
    return mobile_upload()


@app.route("/api/mobile/login", methods=["POST"])
def mobile_login():
    """POST /api/mobile/login — returns JWT token for mobile app."""
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_pw(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401
    token = make_token(user["id"], bool(user["is_admin"]))
    api_key = hashlib.md5(f"ff-{user['id']}".encode()).hexdigest()
    return jsonify({
        "token": token,
        "api_key": api_key,
        "user_id": user["id"],
        "email": user["email"],
        "name": user["full_name"] or user["email"],
        "plan": user["plan"],
        "is_admin": bool(user["is_admin"]),
    })


@app.route("/api/mobile/register", methods=["POST"])
def mobile_register():
    """POST /api/mobile/register — register from mobile app."""
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    full_name = d.get("full_name", "") or d.get("name", "")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    db = get_db()
    try:
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        is_founding = 1 if user_count < 100 else 0
        trial_days = 90 if is_founding else 7
        trial_ends = int(time.time()) + trial_days * 86400
        ref_code = secrets.token_hex(4).upper()
        db.execute(
            "INSERT INTO users (email, password_hash, full_name, is_founding_member, trial_ends_at, referral_code) VALUES (?,?,?,?,?,?)",
            (email, hash_pw(password), full_name, is_founding, trial_ends, ref_code))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        uid = user["id"]
        token = make_token(uid)
        api_key = hashlib.md5(f"ff-{uid}".encode()).hexdigest()
        return jsonify({
            "token": token,
            "api_key": api_key,
            "user_id": uid,
            "email": email,
            "plan": "starter",
            "trial_days": trial_days,
        })
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return jsonify({"error": "Email already registered"}), 400
        return jsonify({"error": str(e)}), 500


@app.route("/api/mobile/videos")
@mobile_login_required
def mobile_videos():
    """GET /api/mobile/videos — list user's videos."""
    db = get_db()
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    rows = db.execute(
        "SELECT v.id, v.title, v.type, v.status, v.youtube_id, v.youtube_url, "
        "v.created_at, c.channel_name FROM videos v "
        "LEFT JOIN channels c ON v.channel_id=c.id "
        "WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT ? OFFSET ?",
        (request.uid, limit, offset)).fetchall()
    queue = db.execute(
        "SELECT id, status, progress, niche, video_type, created_at FROM queue "
        "WHERE user_id=? AND status IN ('pending','processing') ORDER BY created_at DESC LIMIT 10",
        (request.uid,)).fetchall()
    return jsonify({
        "videos": [dict(r) for r in rows],
        "queue": [dict(q) for q in queue],
        "total": db.execute("SELECT COUNT(*) FROM videos WHERE user_id=?", (request.uid,)).fetchone()[0],
    })


def _email_sequence_worker():

    pass
    """Background thread: send Day 1 / Day 3 / Day 7 emails."""
    import datetime
    while True:
        pass
        try:
            pass
            pass
            db = get_db()
            now = int(time.time())
            sequences = db.execute(
                "SELECT es.id, es.user_id, es.day, u.email, u.full_name, u.created_at "
                "FROM email_sequences es JOIN users u ON es.user_id=u.id "
                "WHERE es.sent=0").fetchall()
            for seq in sequences:
                pass
                try:
                    pass
                    pass
                    created_ts = int(datetime.datetime.fromisoformat(
                        str(seq["created_at"])).timestamp())
                except Exception:
                    pass
                    created_ts = now
                send_after = created_ts + seq["day"] * 86400
                if now >= send_after:
                    pass
                    day = seq["day"]
                    subjects = {
                        1: "Welcome! Here's how to make your first video today",
                        3: "3 tips for viral finance content",
                        7: "How is it going? Tips to grow faster",
                    }
                    bodies = {
                        1: f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
                               <h2 style="color:#4F46E5">Your first video is just 3 clicks away</h2>
                               <p>Connect your YouTube channel, pick your niche, and hit Generate. That's it.</p>
                               <a href="{APP_URL}/dashboard" style="background:#4F46E5;color:white;padding:12px 24px;text-decoration:none;border-radius:8px;display:inline-block">
                                   Create My First Video →</a></div>""", 3: f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
                               <h2 style="color:#4F46E5">3 tips for going viral on finance</h2>
                               <ol><li>Post Shorts daily — algorithm rewards consistency</li>
                               <li>Use punchy hooks in the first 2 seconds</li>
                               <li>Niche down: crypto outperforms generic "money tips"</li></ol>
                               <a href="{APP_URL}/dashboard" style="background:#4F46E5;color:white;padding:12px 24px;text-decoration:none;border-radius:8px;display:inline-block">
                                   Generate Videos Now →</a></div>""", 7: f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
                               <h2 style="color:#4F46E5">One week in — keep the momentum!</h2>
                               <p>The channels that post daily for 30 days see 10x more subscribers.
                               Enable Autopilot and let FinanceFlow do the work for you.</p>
                               <a href="{APP_URL}/dashboard" style="background:#4F46E5;color:white;padding:12px 24px;text-decoration:none;border-radius:8px;display:inline-block">
                                   Enable Autopilot →</a></div>""", }
                    subj = subjects.get(
                        day, f"Day {day} tips from FinanceFlow")
                    body = bodies.get(day, "")
                    if body:
                        pass
                        send_email(seq["email"], seq["full_name"]
                                   or seq["email"], subj, body)
                    db.execute(
                        "UPDATE email_sequences SET sent=1, sent_at=CURRENT_TIMESTAMP WHERE id=?",
                        (seq["id"],
                         ))
                    db.commit()
        except Exception as e:
            pass
            print(f"[EMAIL SEQ] Error: {e}")
        time.sleep(3600)  # Check every hour


def _trial_expiry_worker():

    pass
    """Background thread: downgrade users whose trial has expired."""
    while True:
        pass
        try:
            pass
            pass
            db = get_db()
            now = int(time.time())
            db.execute(
                "UPDATE users SET plan='starter' WHERE trial_ends_at > 0 AND trial_ends_at < ? "
                "AND plan IN ('pro','agency')", (now,))
            db.commit()
        except Exception as e:
            pass
            print(f"[TRIAL EXPIRY] Error: {e}")
        time.sleep(3600)


if DATABASE_URL and HAS_PG:
    print(f"[DB] Using PostgreSQL — {DATABASE_URL[:40]}...")
else:
    print(f"[DB] Using SQLite — {DB}")

init_db()

# Start background threads and register them for worker_online_status()
_t1 = threading.Thread(target=_email_sequence_worker, daemon=True)
_t2 = threading.Thread(target=_trial_expiry_worker, daemon=True)
_t1.start()
_t2.start()
_bg_threads.extend([_t1, _t2])

if __name__ == "__main__":

    pass
    pass
    app.run(
        debug=False,
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000)))
