#!/usr/bin/env python3
"""
💰 FinanceFlow SaaS — Full Launch Version
- Admin panel: unlimited everything, manage all users
- Social media cross-posting per channel
- Custom prompts on Pro/Agency
- Port 5001 (avoids Mac AirPlay conflict)
"""

from flask import Flask, request, jsonify, session, redirect, render_template
import sqlite3, hashlib, secrets, json, os, urllib.parse, urllib.request, time
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "financeflow_secret_2025_xK9mP3")
DB    = os.environ.get("DB_PATH", "financeflow.db")
PORT  = int(os.environ.get("PORT", 5001))
HBEAT = "worker_heartbeat.txt"

# ── YOUR ADMIN EMAIL (unlimited free access forever) ──────────
ADMIN_EMAIL = "howtodoprogramming@gmail.com"

PLANS = {
    "starter": {"name":"Starter","price":0,  "channels":1, "videos_per_week":3,  "custom_prompts":False,"social_posting":False},
    "pro":     {"name":"Pro",    "price":29, "channels":3, "videos_per_week":14, "custom_prompts":True, "social_posting":True},
    "agency":  {"name":"Agency", "price":99, "channels":10,"videos_per_week":999,"custom_prompts":True, "social_posting":True},
    "admin":   {"name":"Admin",  "price":0,  "channels":999,"videos_per_week":9999,"custom_prompts":True,"social_posting":True},
}

SOCIAL_PLATFORMS = ["twitter","facebook","instagram","tiktok"]

# ── DB ────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        name TEXT, plan TEXT DEFAULT 'starter',
        api_key TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, channel_name TEXT, channel_id TEXT,
        access_token TEXT, refresh_token TEXT,
        niche TEXT DEFAULT 'personal_finance',
        voice_style TEXT DEFAULT 'professional',
        upload_schedule TEXT DEFAULT 'daily',
        videos_uploaded INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, channel_id INTEGER,
        title TEXT, type TEXT DEFAULT 'short',
        status TEXT DEFAULT 'pending',
        youtube_id TEXT, youtube_url TEXT,
        script TEXT, error_msg TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
        video_type TEXT DEFAULT 'short',
        niche TEXT DEFAULT 'personal_finance',
        custom_prompt TEXT, custom_title TEXT,
        status TEXT DEFAULT 'pending',
        progress TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS prompt_library (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL, prompt TEXT NOT NULL,
        niche TEXT DEFAULT 'personal_finance',
        used_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS social_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        credentials TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (channel_id) REFERENCES channels(id)
    );
    CREATE TABLE IF NOT EXISTS social_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER,
        channel_id INTEGER,
        platform TEXT,
        post_id TEXT,
        post_url TEXT,
        status TEXT DEFAULT 'pending',
        error_msg TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Safe migrations
    for tbl, col in [
        ("queue","custom_prompt TEXT"),("queue","custom_title TEXT"),
        ("queue","progress TEXT DEFAULT ''"),("videos","error_msg TEXT"),
    ]:
        try: db.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
        except: pass
    db.commit(); db.close()

# ── AUTH ──────────────────────────────────────────────────────
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if "user_id" not in session:
            return (jsonify({"error":"Login required"}),401) if request.is_json else redirect("/")
        return f(*args, **kwargs)
    return dec

def admin_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if "user_id" not in session: return redirect("/")
        user = me()
        if not user or user["email"] != ADMIN_EMAIL:
            return jsonify({"error":"Admin only"}),403
        return f(*args, **kwargs)
    return dec

def me():
    if "user_id" not in session: return None
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    db.close(); return u

def get_plan(user):
    """Admin gets unlimited plan regardless of DB"""
    if user["email"] == ADMIN_EMAIL:
        return PLANS["admin"]
    return PLANS.get(user["plan"], PLANS["starter"])

def worker_online():
    try:
        with open(HBEAT) as f: return (time.time()-float(f.read().strip()))<30
    except: return False

# ── PAGES ─────────────────────────────────────────────────────
@app.route("/")
def landing():
    if "user_id" in session: return redirect("/dashboard")
    return render_template("landing.html", plans=PLANS)

@app.route("/dashboard")
@login_required
def dashboard():
    user = me()
    plan = get_plan(user)
    db   = get_db()
    channels = db.execute("SELECT * FROM channels WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    videos   = db.execute("""
        SELECT v.*,c.channel_name FROM videos v
        LEFT JOIN channels c ON v.channel_id=c.id
        WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 30
    """, (user["id"],)).fetchall()
    queue = db.execute("""
        SELECT q.*,c.channel_name FROM queue q
        LEFT JOIN channels c ON q.channel_id=c.id
        WHERE q.user_id=? AND q.status IN ('pending','processing')
        ORDER BY q.created_at ASC
    """, (user["id"],)).fetchall()
    prompts = db.execute("SELECT * FROM prompt_library WHERE user_id=? ORDER BY used_count DESC LIMIT 30", (user["id"],)).fetchall()
    # Social accounts per channel
    social = {}
    for ch in channels:
        accs = db.execute("SELECT * FROM social_accounts WHERE channel_id=? AND active=1", (ch["id"],)).fetchall()
        social[ch["id"]] = [dict(a) for a in accs]
    stats = {
        "total":    db.execute("SELECT COUNT(*) FROM videos WHERE user_id=?", (user["id"],)).fetchone()[0],
        "uploaded": db.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND status='uploaded'", (user["id"],)).fetchone()[0],
        "pending":  db.execute("SELECT COUNT(*) FROM queue WHERE user_id=? AND status IN ('pending','processing')", (user["id"],)).fetchone()[0],
        "channels": len(channels),
    }
    db.close()
    is_admin = user["email"] == ADMIN_EMAIL
    return render_template("dashboard.html",
        user=user, channels=channels, videos=videos, queue=queue,
        stats=stats, plan=plan, plans=PLANS, prompts=prompts,
        social=social, is_admin=is_admin, worker_online=worker_online(),
        success=request.args.get("success"), error=request.args.get("error"))

@app.route("/admin")
@admin_required
def admin_panel():
    db = get_db()
    users    = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    channels = db.execute("SELECT c.*,u.email FROM channels c JOIN users u ON c.user_id=u.id ORDER BY c.created_at DESC").fetchall()
    videos   = db.execute("SELECT v.*,u.email,c.channel_name FROM videos v JOIN users u ON v.user_id=u.id LEFT JOIN channels c ON v.channel_id=c.id ORDER BY v.created_at DESC LIMIT 50").fetchall()
    stats = {
        "total_users":    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_channels": db.execute("SELECT COUNT(*) FROM channels").fetchone()[0],
        "total_videos":   db.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
        "uploaded":       db.execute("SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0],
        "pro_users":      db.execute("SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0],
        "agency_users":   db.execute("SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0],
    }
    mrr = stats["pro_users"]*29 + stats["agency_users"]*99
    db.close()
    return render_template("admin.html", users=users, channels=channels, videos=videos, stats=stats, mrr=mrr, plans=PLANS)

# ── AUTH API ──────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    d = request.json or {}
    email = d.get("email","").lower().strip()
    pw    = d.get("password","")
    name  = d.get("name","")
    if not email or not pw: return jsonify({"error":"Email and password required"}),400
    if len(pw)<6: return jsonify({"error":"Password must be 6+ characters"}),400
    db = get_db()
    try:
        plan = "admin" if email==ADMIN_EMAIL else "starter"
        db.execute("INSERT INTO users (email,password,name,api_key,plan) VALUES (?,?,?,?,?)",
                   (email, hash_pw(pw), name, "ff_"+secrets.token_hex(16), plan))
        db.commit()
        u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        session["user_id"] = u["id"]
        return jsonify({"success":True,"redirect":"/dashboard"})
    except sqlite3.IntegrityError:
        return jsonify({"error":"Email already registered"}),400
    finally: db.close()

@app.route("/api/login", methods=["POST"])
def login():
    d = request.json or {}
    email = d.get("email","").lower().strip()
    pw    = d.get("password","")
    db = get_db()
    u  = db.execute("SELECT * FROM users WHERE email=? AND password=?", (email, hash_pw(pw))).fetchone()
    db.close()
    if not u: return jsonify({"error":"Invalid email or password"}),401
    session["user_id"] = u["id"]
    return jsonify({"success":True,"redirect":"/dashboard"})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success":True,"redirect":"/"})

# ── CHANNELS ──────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

@app.route("/api/channels/connect")
@login_required
def connect_channel():
    user = me(); plan = get_plan(user)
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM channels WHERE user_id=?", (user["id"],)).fetchone()[0]
    db.close()
    if count >= plan["channels"]:
        return jsonify({"error":f"Your {plan['name']} plan supports {plan['channels']} channel(s). Upgrade to add more."}),403
    base  = request.host_url.rstrip("/")
    redir = f"{base}/api/channels/callback"
    state = f"{session['user_id']}:{secrets.token_hex(8)}"
    session["oauth_state"] = state
    url = "https://accounts.google.com/o/oauth2/auth?"+urllib.parse.urlencode({
        "client_id":CLIENT_ID,"redirect_uri":redir,"response_type":"code",
        "scope":"https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        "access_type":"offline","prompt":"consent","state":state
    })
    return jsonify({"auth_url":url})

@app.route("/api/channels/callback")
def channel_callback():
    code  = request.args.get("code")
    state = request.args.get("state","")
    if request.args.get("error") or not code:
        return redirect("/dashboard?error=auth_cancelled")
    user_id = state.split(":")[0]
    if not user_id: return redirect("/dashboard?error=invalid_state")
    base  = request.host_url.rstrip("/")
    redir = f"{base}/api/channels/callback"
    try:
        data = urllib.parse.urlencode({"code":code,"client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,
            "redirect_uri":redir,"grant_type":"authorization_code"}).encode()
        with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token",data=data,
            headers={"Content-Type":"application/x-www-form-urlencoded"})) as r:
            tokens = json.loads(r.read())
        access=tokens.get("access_token",""); refresh=tokens.get("refresh_token","")
        with urllib.request.urlopen(urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers={"Authorization":f"Bearer {access}"})) as r:
            cdata = json.loads(r.read())
        ch_name,ch_id = "My Channel",""
        if cdata.get("items"):
            ch_name=cdata["items"][0]["snippet"]["title"]; ch_id=cdata["items"][0]["id"]
        db=get_db()
        db.execute("INSERT INTO channels (user_id,channel_name,channel_id,access_token,refresh_token) VALUES (?,?,?,?,?)",
                   (user_id,ch_name,ch_id,access,refresh))
        db.commit(); db.close()
        return redirect("/dashboard?success=channel_connected")
    except Exception as e:
        print(f"Channel connect error: {e}")
        return redirect("/dashboard?error=connect_failed")

@app.route("/api/channels/<int:cid>", methods=["DELETE"])
@login_required
def delete_channel(cid):
    user=me(); db=get_db()
    db.execute("DELETE FROM channels WHERE id=? AND user_id=?",(cid,user["id"]))
    db.commit(); db.close()
    return jsonify({"success":True})

@app.route("/api/channels/<int:cid>/settings", methods=["POST"])
@login_required
def update_channel(cid):
    user=me(); d=request.json or {}; db=get_db()
    db.execute("UPDATE channels SET niche=?,voice_style=?,upload_schedule=? WHERE id=? AND user_id=?",
               (d.get("niche"),d.get("voice_style"),d.get("upload_schedule"),cid,user["id"]))
    db.commit(); db.close()
    return jsonify({"success":True})

# ── SOCIAL MEDIA ──────────────────────────────────────────────
@app.route("/api/channels/<int:cid>/social", methods=["GET"])
@login_required
def get_social(cid):
    user=me(); db=get_db()
    ch=db.execute("SELECT id FROM channels WHERE id=? AND user_id=?",(cid,user["id"])).fetchone()
    if not ch: db.close(); return jsonify({"error":"Channel not found"}),404
    accs=db.execute("SELECT * FROM social_accounts WHERE channel_id=?",(cid,)).fetchall()
    db.close()
    result={}
    for a in accs:
        creds=json.loads(a["credentials"])
        result[a["platform"]]={"active":a["active"],"configured":True,"display":creds.get("display","")}
    return jsonify(result)

@app.route("/api/channels/<int:cid>/social", methods=["POST"])
@login_required
def save_social(cid):
    user=me()
    plan=get_plan(user)
    if not plan["social_posting"] and user["email"]!=ADMIN_EMAIL:
        return jsonify({"error":"Social posting requires Pro or Agency plan"}),403
    d=request.json or {}
    platform=d.get("platform","")
    creds=d.get("credentials",{})
    active=d.get("active",1)
    if platform not in SOCIAL_PLATFORMS:
        return jsonify({"error":"Invalid platform"}),400
    db=get_db()
    ch=db.execute("SELECT id FROM channels WHERE id=? AND user_id=?",(cid,user["id"])).fetchone()
    if not ch: db.close(); return jsonify({"error":"Channel not found"}),404
    existing=db.execute("SELECT id FROM social_accounts WHERE channel_id=? AND platform=?",(cid,platform)).fetchone()
    if existing:
        db.execute("UPDATE social_accounts SET credentials=?,active=? WHERE channel_id=? AND platform=?",
                   (json.dumps(creds),active,cid,platform))
    else:
        db.execute("INSERT INTO social_accounts (channel_id,platform,credentials,active) VALUES (?,?,?,?)",
                   (cid,platform,json.dumps(creds),active))
    db.commit(); db.close()
    return jsonify({"success":True})

@app.route("/api/channels/<int:cid>/social/<platform>", methods=["DELETE"])
@login_required
def remove_social(cid,platform):
    user=me(); db=get_db()
    db.execute("DELETE FROM social_accounts WHERE channel_id=? AND platform=?",(cid,platform))
    db.commit(); db.close()
    return jsonify({"success":True})

# ── GENERATE ──────────────────────────────────────────────────
@app.route("/api/videos/generate", methods=["POST"])
@login_required
def generate_video():
    user=me(); d=request.json or {}
    channel_id    = d.get("channel_id")
    video_type    = d.get("type","short")
    custom_prompt = (d.get("custom_prompt") or "").strip()
    custom_title  = (d.get("custom_title")  or "").strip()
    plan = get_plan(user)
    if not channel_id:
        return jsonify({"error":"Please select a channel first."}),400
    if custom_prompt and not plan["custom_prompts"]:
        return jsonify({"error":"Custom prompts require Pro or Agency plan."}),403
    db=get_db()
    ch=db.execute("SELECT * FROM channels WHERE id=? AND user_id=?",(channel_id,user["id"])).fetchone()
    if not ch: db.close(); return jsonify({"error":"Channel not found"}),404
    if user["email"]!=ADMIN_EMAIL:
        week=db.execute("SELECT COUNT(*) FROM queue WHERE user_id=? AND created_at>datetime('now','-7 days') AND status!='cancelled'",(user["id"],)).fetchone()[0]
        if week>=plan["videos_per_week"]:
            db.close(); return jsonify({"error":f"Weekly limit of {plan['videos_per_week']} videos reached."}),403
    db.execute("INSERT INTO queue (user_id,channel_id,video_type,niche,custom_prompt,custom_title,status,progress) VALUES (?,?,?,?,?,?,'pending','⏳ Waiting in queue...')",
               (user["id"],channel_id,video_type,ch["niche"],custom_prompt or None,custom_title or None))
    db.commit(); db.close()
    return jsonify({"success":True,"message":"✅ Added to queue! Worker processing shortly."})

@app.route("/api/queue/status")
@login_required
def queue_status():
    user=me(); db=get_db()
    queue  = db.execute("SELECT q.*,c.channel_name FROM queue q LEFT JOIN channels c ON q.channel_id=c.id WHERE q.user_id=? ORDER BY q.created_at DESC LIMIT 20",(user["id"],)).fetchall()
    videos = db.execute("SELECT v.*,c.channel_name FROM videos v LEFT JOIN channels c ON v.channel_id=c.id WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 15",(user["id"],)).fetchall()
    stats  = {
        "total":    db.execute("SELECT COUNT(*) FROM videos WHERE user_id=?",(user["id"],)).fetchone()[0],
        "uploaded": db.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND status='uploaded'",(user["id"],)).fetchone()[0],
        "pending":  db.execute("SELECT COUNT(*) FROM queue WHERE user_id=? AND status IN ('pending','processing')",(user["id"],)).fetchone()[0],
    }
    db.close()
    return jsonify({"queue":[dict(q) for q in queue],"videos":[dict(v) for v in videos],"stats":stats,"worker_online":worker_online()})

@app.route("/api/queue/<int:qid>/cancel", methods=["POST"])
@login_required
def cancel_job(qid):
    user=me(); db=get_db()
    db.execute("UPDATE queue SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'",(qid,user["id"]))
    db.commit(); db.close()
    return jsonify({"success":True})

# ── PROMPTS ───────────────────────────────────────────────────
@app.route("/api/prompts", methods=["GET"])
@login_required
def get_prompts():
    user=me(); db=get_db()
    p=db.execute("SELECT * FROM prompt_library WHERE user_id=? ORDER BY used_count DESC",(user["id"],)).fetchall()
    db.close(); return jsonify([dict(x) for x in p])

@app.route("/api/prompts", methods=["POST"])
@login_required
def save_prompt():
    user=me()
    if not get_plan(user)["custom_prompts"]:
        return jsonify({"error":"Prompt library requires Pro plan"}),403
    d=request.json or {}
    title=d.get("title","").strip(); prompt=d.get("prompt","").strip(); niche=d.get("niche","personal_finance")
    if not title or not prompt: return jsonify({"error":"Title and prompt required"}),400
    db=get_db()
    db.execute("INSERT INTO prompt_library (user_id,title,prompt,niche) VALUES (?,?,?,?)",(user["id"],title,prompt,niche))
    db.commit(); db.close()
    return jsonify({"success":True})

@app.route("/api/prompts/<int:pid>", methods=["DELETE"])
@login_required
def del_prompt(pid):
    user=me(); db=get_db()
    db.execute("DELETE FROM prompt_library WHERE id=? AND user_id=?",(pid,user["id"]))
    db.commit(); db.close(); return jsonify({"success":True})

# ── ACCOUNT ───────────────────────────────────────────────────
@app.route("/api/account/upgrade", methods=["POST"])
@login_required
def upgrade_plan():
    user=me(); d=request.json or {}
    plan=d.get("plan")
    if plan not in PLANS: return jsonify({"error":"Invalid plan"}),400
    db=get_db()
    db.execute("UPDATE users SET plan=? WHERE id=?",(plan,user["id"]))
    db.commit(); db.close()
    return jsonify({"success":True,"message":f"Plan changed to {PLANS[plan]['name']}!"})

@app.route("/api/account/password", methods=["POST"])
@login_required
def change_pw():
    user=me(); d=request.json or {}
    curr=d.get("current",""); new=d.get("new","")
    if len(new)<6: return jsonify({"error":"New password must be 6+ chars"}),400
    db=get_db()
    u=db.execute("SELECT id FROM users WHERE id=? AND password=?",(user["id"],hash_pw(curr))).fetchone()
    if not u: db.close(); return jsonify({"error":"Current password incorrect"}),401
    db.execute("UPDATE users SET password=? WHERE id=?",(hash_pw(new),user["id"]))
    db.commit(); db.close(); return jsonify({"success":True})

# ── ADMIN API ─────────────────────────────────────────────────
@app.route("/api/admin/users")
@admin_required
def admin_users():
    db=get_db()
    users=db.execute("SELECT u.*,COUNT(c.id) as ch_count,COUNT(v.id) as vid_count FROM users u LEFT JOIN channels c ON c.user_id=u.id LEFT JOIN videos v ON v.user_id=u.id GROUP BY u.id ORDER BY u.created_at DESC").fetchall()
    db.close(); return jsonify([dict(u) for u in users])

@app.route("/api/admin/users/<int:uid>/plan", methods=["POST"])
@admin_required
def admin_set_plan(uid):
    d=request.json or {}; plan=d.get("plan")
    if plan not in PLANS: return jsonify({"error":"Invalid plan"}),400
    db=get_db()
    db.execute("UPDATE users SET plan=? WHERE id=?",(plan,uid))
    db.commit(); db.close()
    return jsonify({"success":True})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_del_user(uid):
    db=get_db()
    db.execute("DELETE FROM users WHERE id=?",(uid,))
    db.commit(); db.close()
    return jsonify({"success":True})

@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    db=get_db()
    stats={
        "users":    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "channels": db.execute("SELECT COUNT(*) FROM channels").fetchone()[0],
        "videos":   db.execute("SELECT COUNT(*) FROM videos WHERE status='uploaded'").fetchone()[0],
        "pro":      db.execute("SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0],
        "agency":   db.execute("SELECT COUNT(*) FROM users WHERE plan='agency'").fetchone()[0],
        "queue":    db.execute("SELECT COUNT(*) FROM queue WHERE status IN ('pending','processing')").fetchone()[0],
    }
    db.close()
    stats["mrr"]=stats["pro"]*29+stats["agency"]*99
    stats["worker_online"]=worker_online()
    return jsonify(stats)

if __name__=="__main__":
    init_db()
    print("╔══════════════════════════════════════════════╗")
    print(f"║  💰 FinanceFlow  →  http://localhost:{PORT}     ║")
    print(f"║  👑 Admin panel →  http://localhost:{PORT}/admin ║")
    print("╚══════════════════════════════════════════════╝")
    app.run(debug=False, port=PORT)

# ── FORGOT PASSWORD ───────────────────────────────────────────
# Simple token-based reset (no email server needed — admin resets manually)
# Tokens stored in DB, valid 1 hour

@app.route("/reset-password")
def reset_password_page():
    token = request.args.get("token","")
    return f"""<!DOCTYPE html>
<html>
<head>
<title>Reset Password — FinanceFlow</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:#030508;color:#e8eaf0;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.box{{background:#080d18;border:1px solid #1a2235;border-radius:20px;padding:48px;width:100%;max-width:440px}}
.logo{{font-size:22px;font-weight:800;color:#FFD700;margin-bottom:8px}}
h2{{font-size:24px;font-weight:700;margin-bottom:6px}}
p{{color:#6b7280;font-size:14px;margin-bottom:28px}}
input{{width:100%;background:#0d1425;border:1px solid #1a2235;color:#e8eaf0;padding:13px 16px;border-radius:10px;font-size:14px;font-family:'DM Sans',sans-serif;margin-bottom:14px;outline:none}}
input:focus{{border-color:#FFD700}}
button{{width:100%;background:linear-gradient(135deg,#FFD700,#FFA500);color:#000;border:none;padding:14px;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;font-family:'DM Sans',sans-serif}}
.msg{{padding:12px;border-radius:8px;font-size:13px;margin-bottom:14px;display:none}}
.err{{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);color:#ef4444}}
.ok{{background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);color:#10b981}}
a{{color:#FFD700;text-decoration:none;font-size:13px}}
</style>
</head>
<body>
<div class="box">
  <div class="logo">💰 FinanceFlow</div>
  <h2>Set New Password</h2>
  <p>Enter your new password below.</p>
  <div class="msg err" id="err"></div>
  <div class="msg ok" id="ok"></div>
  <input type="password" id="pw" placeholder="New password (6+ characters)">
  <input type="password" id="pw2" placeholder="Confirm new password">
  <input type="hidden" id="token" value="{token}">
  <button onclick="doReset()">Set New Password</button>
  <br><br>
  <a href="/">← Back to login</a>
</div>
<script>
async function doReset(){{
  const pw=document.getElementById('pw').value;
  const pw2=document.getElementById('pw2').value;
  const token=document.getElementById('token').value;
  if(pw.length<6){{show('err','Password must be 6+ characters');return}}
  if(pw!==pw2){{show('err','Passwords do not match');return}}
  const r=await fetch('/api/reset-password',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token,password:pw}})}});
  const d=await r.json();
  if(d.success){{show('ok','✅ Password changed! Redirecting...');setTimeout(()=>location.href='/',2000)}}
  else show('err',d.error||'Failed');
}}
function show(id,msg){{
  document.getElementById('err').style.display='none';
  document.getElementById('ok').style.display='none';
  const el=document.getElementById(id);
  el.textContent=msg;el.style.display='block';
}}
</script>
</body>
</html>"""

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    d = request.json or {}
    email = d.get("email","").lower().strip()
    if not email: return jsonify({"error":"Email required"}),400
    db = get_db()
    u = db.execute("SELECT id,name FROM users WHERE email=?",(email,)).fetchone()
    if not u:
        db.close()
        # Don't reveal if email exists
        return jsonify({"success":True,"message":"If that email exists, a reset link has been sent."})
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + 3600  # 1 hour
    try: db.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    except: pass
    try: db.execute("ALTER TABLE users ADD COLUMN reset_expires INTEGER")
    except: pass
    db.execute("UPDATE users SET reset_token=?,reset_expires=? WHERE id=?",(token,expires,u["id"]))
    db.commit(); db.close()
    base = request.host_url.rstrip("/")
    reset_url = f"{base}/reset-password?token={token}"
    # Store in a simple way - admin can see it, or we log it
    print(f"\n🔑 PASSWORD RESET for {email}:\n   {reset_url}\n")
    # If SMTP configured, send email - otherwise return URL directly for now
    smtp_user = os.environ.get("SMTP_USER","")
    if smtp_user:
        try:
            import smtplib
            from email.mime.text import MIMEText
            smtp_pass = os.environ.get("SMTP_PASS","")
            smtp_host = os.environ.get("SMTP_HOST","smtp.gmail.com")
            msg = MIMEText(f"Click to reset your FinanceFlow password:\n\n{reset_url}\n\nThis link expires in 1 hour.")
            msg["Subject"] = "Reset your FinanceFlow password"
            msg["From"] = smtp_user
            msg["To"] = email
            with smtplib.SMTP_SSL(smtp_host, 465) as s:
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)
            return jsonify({"success":True,"message":"Reset link sent to your email!"})
        except Exception as e:
            print(f"Email error: {e}")
    # No SMTP — return the link directly (works for testing, replace with email later)
    return jsonify({"success":True,"message":"Reset link generated!","reset_url":reset_url})

@app.route("/api/reset-password", methods=["POST"])
def do_reset_password():
    d = request.json or {}
    token = d.get("token","")
    password = d.get("password","")
    if len(password)<6: return jsonify({"error":"Password must be 6+ characters"}),400
    if not token: return jsonify({"error":"Invalid reset link"}),400
    db = get_db()
    try:
        u = db.execute("SELECT id,reset_expires FROM users WHERE reset_token=?",(token,)).fetchone()
    except: u = None
    if not u: db.close(); return jsonify({"error":"Invalid or expired reset link"}),400
    if int(time.time()) > (u["reset_expires"] or 0):
        db.close(); return jsonify({"error":"Reset link has expired. Request a new one."}),400
    db.execute("UPDATE users SET password=?,reset_token=NULL,reset_expires=NULL WHERE id=?",(hash_pw(password),u["id"]))
    db.commit(); db.close()
    return jsonify({"success":True})
