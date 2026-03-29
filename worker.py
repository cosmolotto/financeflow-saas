#!/usr/bin/env python3
"""
⚡ FinanceFlow Worker — Complete Launch Version
Handles: voice, music, frames, render, YouTube upload, social media cross-posting
"""

import os, sys, json, sqlite3, subprocess, time, wave, struct, math, random
import hmac, hashlib, base64, secrets, urllib.parse, urllib.request, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── Paths: always relative to this script, not CWD ──────────────────────
_HERE  = Path(__file__).parent.resolve()
DB     = str(_HERE / "financeflow.db")
OUT    = _HERE / "generated_videos"
HBEAT  = str(_HERE / "worker_heartbeat.txt")
OUT.mkdir(exist_ok=True)

# ── PostgreSQL support (Railway production) ──────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
_HAS_PG = False
if DATABASE_URL:
    try:
        import psycopg2, psycopg2.extras
        _HAS_PG = True
    except ImportError:
        print("[WARN] DATABASE_URL set but psycopg2 not installed — falling back to SQLite")
        DATABASE_URL = ""

CLIENT_ID       = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET   = os.environ.get("GOOGLE_CLIENT_SECRET", "")
ELEVENLABS_KEY     = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
OPENAI_KEY         = os.environ.get("OPENAI_API_KEY", "")

def find_ffmpeg():
    import shutil
    # Try system ffmpeg first (Railway installs via nixpacks)
    system = shutil.which('ffmpeg')
    if system:
        return system
    # Try common paths
    for p in [
        '/root/.nix-profile/bin/ffmpeg',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        os.path.expanduser('~/Downloads/ffmpeg')
    ]:
        if os.path.exists(p):
            return p
    return None
FFMPEG = find_ffmpeg()

_FONT_CACHE = {}
def fnt(size):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Supplemental/Impact.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try:
            f = ImageFont.truetype(p, size)
            _FONT_CACHE[size] = f
            return f
        except: pass
    f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f

# Per-niche visual themes
NICHE_THEMES = {
    "personal_finance": {"bg": (8, 8, 8),   "bg2": (25, 18, 4),  "grid": (35, 28, 8)},
    "crypto":           {"bg": (5, 3, 18),  "bg2": (18, 8, 32),  "grid": (28, 15, 45)},
    "real_estate":      {"bg": (4, 14, 4),  "bg2": (12, 28, 10), "grid": (12, 38, 12)},
    "side_hustle":      {"bg": (14, 7, 3),  "bg2": (28, 14, 4),  "grid": (42, 22, 5)},
    "financeflow_promo":{"bg": (4, 4, 18),  "bg2": (12, 10, 32), "grid": (22, 20, 48)},
}
NICHE_LABELS = {
    "personal_finance": "FINANCE TIPS",
    "crypto":           "CRYPTO TIPS",
    "real_estate":      "REAL ESTATE TIPS",
    "side_hustle":      "SIDE HUSTLE TIPS",
    "financeflow_promo":"FINANCEFLOW AI",
}

SCRIPTS = {
"personal_finance": [
  {"title":"You're Wasting $200 Every Month Without Knowing It","script":"Stop. You are literally wasting 200 dollars every single month without knowing it. Open your bank app right now and look at every single recurring charge. I guarantee you have at least 3 subscriptions you forgot about. Cancel everything you haven't used in 30 days. That is 2,400 dollars a year back in your pocket.","color":(160,15,15),"accent":(255,215,0),"lines":["YOU'RE WASTING","$200/MONTH","OPEN YOUR BANK","APP RIGHT NOW","CANCEL ALL","FORGOTTEN SUBS","= $2,400/YEAR","BACK TO YOU"]},
  {"title":"The $5 Coffee Is Costing You $50,000","script":"That 5 dollar coffee is costing you 50,000 dollars. 5 dollars a day is 150 a month. Invested at 10 percent annually for 30 years that becomes over 50,000 dollars. I am not saying stop drinking coffee. I am saying understand the true cost of every daily habit. Small amounts compounded create life-changing wealth.","color":(70,30,5),"accent":(255,200,50),"lines":["$5 COFFEE","IS COSTING YOU","$50,000","$5/DAY =","$150/MONTH","AT 10% 30 YRS","= $50,000+","KNOW YOUR COSTS"]},
  {"title":"Your Savings Account Is Robbing You Blind","script":"Your savings account is quietly robbing you. It pays 0.01 percent interest while inflation runs at 3 to 4 percent. Your money is losing purchasing power every single day. Open a high yield savings account paying 4 to 5 percent today. On 10,000 dollars that is the difference between earning 1 dollar versus 500 dollars a year. Same money, zero extra risk.","color":(8,50,110),"accent":(100,200,255),"lines":["YOUR SAVINGS","ROBBING YOU","NORMAL BANK","= 0.01%","INFLATION","= 3-4%/YEAR","HIGH YIELD","= 5% FIX NOW"]},
  {"title":"Invest $100 Today — Here's Exactly How","script":"If you have 100 dollars right now here is exactly how to invest it. Open Fidelity, free account zero minimums. Buy FZROX, total market index fund with zero fees. Set up automatic 50 dollar monthly contributions. Leave it alone forever. 100 dollars at 10 percent annual return becomes 1,700 in 30 years. Add 50 monthly and you hit over 100,000 dollars.","color":(0,70,35),"accent":(100,255,150),"lines":["$100 TO INVEST?","OPEN FIDELITY","FREE ACCOUNT","BUY FZROX","ZERO FEES","AUTO $50/MONTH","30 YEARS =","$100,000+"]},
  {"title":"3 Numbers That Predict Your Financial Future","script":"Three numbers predict your entire financial future. Credit score, below 700 and you pay thousands extra in interest on every loan. Savings rate, less than 20 percent and you will likely work until 65. Net worth, is it growing month over month? If not it is shrinking. Check all three today and fix the weakest one first.","color":(35,0,70),"accent":(180,100,255),"lines":["3 NUMBERS","PREDICT YOUR","FINANCIAL FUTURE","1: CREDIT >700","2: SAVE >20%","3: NET WORTH","GROWING?","CHECK TODAY"]},
  {"title":"Why 95% of People Stay Broke Forever","script":"The brutal truth about why 95 percent of people stay broke. They trade time for money and never escape. They buy liabilities and call them assets. They spend raises instead of investing them. They wait until they have more money to start. Wealthy people start with whatever they have right now, even if it is just 20 dollars a month.","color":(120,10,10),"accent":(255,215,0),"lines":["WHY 95% STAY","BROKE FOREVER","TRADE TIME","FOR MONEY","BUY LIABILITIES","SPEND RAISES","WAIT TO START","START WITH $20"]},
  {"title":"The Credit Score Hack Nobody Tells You","script":"The credit score hack nobody talks about. Most people think paying bills on time is enough. But the second biggest factor is credit utilization, how much of your limit you actually use. Keep it under 10 percent and your score climbs fast. On a 1000 dollar limit never carry more than 100 balance. Do this for 90 days and your score could jump 50 to 80 points.","color":(0,60,100),"accent":(50,200,255),"lines":["CREDIT HACK","NOBODY TELLS YOU","USE LESS THAN","10% OF YOUR LIMIT","$1000 LIMIT?","MAX $100 BAL","90 DAYS =","+50-80 POINTS"]},
],
"crypto": [
  {"title":"Bitcoin Explained in 60 Seconds","script":"Bitcoin in 60 seconds. Bitcoin is digital money no government or bank controls. There will only ever be 21 million Bitcoin. That scarcity is what gives it value. Every 4 years the rate of new Bitcoin creation gets cut in half, this is called the halving. Historically every halving has been followed by a major price increase. You can buy as little as 10 dollars worth.","color":(160,70,0),"accent":(255,160,0),"lines":["BITCOIN IN","60 SECONDS","DIGITAL MONEY","NO BANK CONTROLS","ONLY 21M EXIST","HALVING = PRICE","INCREASES","BUY FROM $10"]},
  {"title":"5 Crypto Mistakes That Will Drain You","script":"Five crypto mistakes that drain beginners. One, buying based on hype not research. Two, putting everything in one coin. Three, leaving coins on exchanges instead of your own wallet. Four, panic selling during dips. Five, not understanding what you actually own. The people who made real money in crypto did the opposite of all five.","color":(100,0,100),"accent":(200,100,255),"lines":["5 CRYPTO MISTAKES","THAT DRAIN YOU","1: BUYING HYPE","2: ALL ONE COIN","3: ON EXCHANGE","4: PANIC SELL","5: NOT LEARNING","AVOID ALL 5"]},
  {"title":"Ethereum vs Bitcoin — What's the Difference?","script":"Bitcoin vs Ethereum, what is actually different. Bitcoin is digital gold, a store of value with a fixed supply. Ethereum is a programmable blockchain, a platform where developers build apps, NFTs, and DeFi protocols. Bitcoin is the savings account. Ethereum is the operating system. Both have a place in a diversified crypto portfolio. Never put more than 10 percent of your net worth in crypto.","color":(20,60,80),"accent":(50,200,200),"lines":["BITCOIN VS","ETHEREUM","BITCOIN =","DIGITAL GOLD","ETHEREUM =","PROGRAMMABLE","BLOCKCHAIN","MAX 10% NET WORTH"]},
],
"real_estate": [
  {"title":"Real Estate Income Without Buying Property","script":"You can earn real estate income without buying a single property. They are called REITs, Real Estate Investment Trusts. These companies own apartment buildings, shopping centers and warehouses. By law they must pay out 90 percent of income as dividends. You can start with one share, sometimes just 20 to 30 dollars. Rental income with zero tenants, zero maintenance.","color":(15,55,15),"accent":(100,220,100),"lines":["REAL ESTATE INCOME","WITHOUT BUYING","REITS OWN","BUILDINGS","PAY YOU 90%","OF PROFITS","FROM ONE SHARE","NO TENANTS"]},
  {"title":"Buy Your First House With Low Income","script":"You do not need 20 percent down to buy a house. FHA loans allow as little as 3.5 percent down with a 580 credit score. VA loans for veterans require zero down. USDA rural loans also require zero down. The key is your credit score and debt to income ratio. Get credit above 620, keep debt low, and you can own a home sooner than you think.","color":(80,40,0),"accent":(255,160,50),"lines":["FIRST HOUSE","LOW INCOME","NO 20% NEEDED","FHA = 3.5% DOWN","VA LOAN = $0","USDA = $0 DOWN","CREDIT > 620","YOU CAN DO IT"]},
  {"title":"House Hacking — Live Free and Build Wealth","script":"House hacking is the most powerful wealth strategy for beginners. You buy a 2 to 4 unit property, live in one unit and rent out the others. Tenant rent covers your mortgage. You live free while building equity. In 2 years you move out, rent all units and repeat. This is how regular people build real estate portfolios without being rich.","color":(30,60,30),"accent":(150,255,100),"lines":["HOUSE HACKING","LIVE FREE","BUILD WEALTH","BUY 2-4 UNITS","LIVE IN ONE","RENT THE REST","TENANTS PAY","YOUR MORTGAGE"]},
],
"side_hustle": [
  {"title":"Make $500 This Weekend — Zero Experience","script":"How to make 500 dollars this weekend starting from zero. Day one, list everything unused in your home on Facebook Marketplace. Clothes, electronics, furniture. Price 20 percent below similar listings. Most people make 200 to 300 dollars just from stuff they own. Day two, offer car detailing. 20 dollars in supplies, charge 75 to 100 per car. Three cars and you have your 500.","color":(0,55,110),"accent":(50,150,255),"lines":["$500 THIS WEEKEND","ZERO EXPERIENCE","DAY 1: SELL STUFF","FB MARKETPLACE","= $200-300","DAY 2: CAR","DETAILING","3 CARS = $500"]},
  {"title":"5 Side Hustles You Can Start With $0","script":"Five side hustles you can start today with zero money. Freelance writing on Upwork or Fiverr. Virtual assistant work, 15 to 25 dollars per hour. Social media management for local businesses. Reselling thrift store finds on eBay. Tutoring in any subject you know. Any one of these can make 500 to 2000 extra dollars per month within 60 days.","color":(70,0,120),"accent":(180,80,255),"lines":["5 SIDE HUSTLES","START WITH $0","FREELANCING","VA WORK $25/HR","SOCIAL MEDIA MGT","THRIFT RESELL","TUTORING","$500-2000/MONTH"]},
  {"title":"Digital Products — Make Money While You Sleep","script":"Digital products are the best side hustle in 2025. You create something once, a template, guide, preset or course, and sell it forever. Sell on Etsy, Gumroad or your own site. Month one you make 200. Month three you make 800. Month six you could hit 3,000 or more. Zero inventory, zero shipping, pure profit. Anyone with a skill can do this.","color":(100,60,0),"accent":(255,200,50),"lines":["DIGITAL PRODUCTS","MAKE MONEY","WHILE YOU SLEEP","MAKE IT ONCE","SELL FOREVER","MONTH 1 = $200","MONTH 6 = $3K+","ZERO INVENTORY"]},
],
"financeflow_promo": [
  {"title":"I Automated My YouTube Channel With AI — Here's How","script":"I automated my entire YouTube finance channel with AI and it uploads videos while I sleep. The tool is called FinanceFlow. It writes the script, records the voice, generates the video, and uploads it to YouTube automatically. I went from zero videos to posting daily without recording a single thing. Try it free at web-production-39b44.up.railway.app","color":(20,20,60),"accent":(255,215,0),"lines":["I AUTOMATED","MY YOUTUBE","CHANNEL WITH AI","SCRIPTS ✓","VOICE ✓","VIDEO ✓","AUTO-UPLOAD ✓","TRY FREE NOW"]},
  {"title":"This AI Tool Uploads YouTube Videos While I Sleep","script":"What if your YouTube channel uploaded videos automatically every single day without you doing anything? That is exactly what FinanceFlow does. It uses AI to generate finance videos, add voice narration, create thumbnails, and upload to YouTube on autopilot. I have been using it for 30 days and my channel grew without me touching it once. Link in bio — try it free.","color":(10,40,80),"accent":(100,200,255),"lines":["YOUTUBE ON","AUTOPILOT","GENERATE","VOICE","THUMBNAIL","UPLOAD","ALL AUTOMATIC","TRY FREE"]},
  {"title":"FinanceFlow Review — Automated YouTube for Finance","script":"Here is my honest FinanceFlow review after 30 days. It creates finance videos automatically using AI. You connect your YouTube channel, pick a niche like personal finance or crypto, and it handles everything. Scripts, voice, video, upload. The videos look professional. My channel went from zero to 30 videos in 30 days. The free trial is 7 days with no credit card. web-production-39b44.up.railway.app","color":(60,10,10),"accent":(255,215,0),"lines":["FINANCEFLOW","HONEST REVIEW","30 DAYS TESTED","AUTO SCRIPTS","AI VOICE","AUTO UPLOAD","ZERO EFFORT","7-DAY FREE TRIAL"]},
  {"title":"How to Make Money on YouTube Without Recording Videos","script":"You can build a profitable YouTube channel without ever recording a single video. Use AI automation. Tools like FinanceFlow write the scripts, generate AI voice narration, create the visuals, and upload automatically. Finance channels can monetize at 1,000 subscribers and earn thousands per month from ad revenue. Start your automated channel today at web-production-39b44.up.railway.app","color":(0,50,30),"accent":(100,255,150),"lines":["MAKE MONEY","ON YOUTUBE","WITHOUT","RECORDING","AI WRITES","AI SPEAKS","AI UPLOADS","START TODAY"]},
],
# ── Extra built-in scripts (fallback when no OpenAI key) ─────────────────
"personal_finance_extra": [
  {"title":"The 50/30/20 Budget Rule That Changes Everything","script":"The 50 30 20 budget rule is the simplest way to fix your finances. Fifty percent of your income goes to needs: rent, food, utilities. Thirty percent to wants: eating out, entertainment, subscriptions. Twenty percent to savings and debt payoff. On a 3000 dollar monthly income that is 600 dollars automatically building your future. Start this today.","color":(80,20,20),"accent":(255,215,0),"lines":["50/30/20 RULE","CHANGES EVERYTHING","50% NEEDS","30% WANTS","20% SAVINGS","ON $3K/MO","= $600/MO","SAVED AUTO"]},
  {"title":"Why You Need an Emergency Fund Now","script":"Without an emergency fund you are one car repair away from debt. Three to six months of expenses saved in a high yield account is not optional. It is the foundation of your financial life. If you lose your job tomorrow can you pay your bills for three months? If the answer is no then every dollar above your minimum debt payment should go to that fund first.","color":(20,60,100),"accent":(80,180,255),"lines":["EMERGENCY FUND","IS NOT OPTIONAL","NO FUND =","ONE BILL AWAY","FROM DEBT","3-6 MONTHS","EXPENSES SAVED","START NOW"]},
  {"title":"Automate Your Savings — Never Think About It Again","script":"The secret of every wealthy person I have studied is automation. They never decide to save. Saving happens before they can spend. Set up an automatic transfer for the day after your paycheck lands. Even 50 dollars a week is 2600 a year. At 10 percent return in 20 years that is 158,000 dollars. Automate it today and stop relying on willpower.","color":(0,40,80),"accent":(100,200,255),"lines":["AUTOMATE","YOUR SAVINGS","WEALTHY PEOPLE","NEVER DECIDE","TO SAVE","$50/WEEK =","$158K IN 20YRS","SET IT TODAY"]},
  {"title":"Index Funds Beat 96% of Professional Fund Managers","script":"Here is a fact that will shock you. Over the last 20 years 96 percent of actively managed funds failed to beat simple index funds. The S and P 500 has averaged 10 percent annually since 1928. You do not need a financial advisor. Buy VFIAX or VOO every single month. Stay in it forever. That is the entire strategy.","color":(30,10,70),"accent":(180,100,255),"lines":["INDEX FUNDS","BEAT 96% OF","FUND MANAGERS","S&P 500","10%/YR AVG","SINCE 1928","BUY VOO","EVERY MONTH"]},
  {"title":"The Debt Avalanche Method — Pay Off Debt Fastest","script":"There are two ways to pay off debt. Avalanche pays the highest interest rate first while making minimum payments on the rest. Snowball pays the smallest balance first for motivation. Mathematically the avalanche method saves you the most money. On 20,000 of credit card debt at 22 percent you could save 4,000 dollars in interest versus the snowball. The math does not lie.","color":(140,10,10),"accent":(255,180,50),"lines":["DEBT AVALANCHE","SAVES MOST","PAY HIGHEST","RATE FIRST","MIN ON REST","SAVES $4K","ON $20K DEBT","VS SNOWBALL"]},
  {"title":"What Rich People Buy That Poor People Don't","script":"Rich people buy assets. Poor people buy liabilities that look like assets. Rich people buy stocks, real estate, businesses. Poor people buy new cars, designer clothes, gadgets that depreciate. The difference is simple: assets put money in your pocket every month. Liabilities take money out. Before any major purchase ask yourself which one this is.","color":(100,60,0),"accent":(255,200,50),"lines":["ASSETS VS","LIABILITIES","RICH BUY","STOCKS REITS","BUSINESSES","POOR BUY","DEPRECIATING","STUFF"]},
  {"title":"The 1% Rule for Instant Wealth Building","script":"You do not need a huge income to build wealth. You need the one percent rule. Increase your savings rate by just one percent every month. Month one save ten percent. Month two save eleven. By month twelve you are saving twenty two percent of your income automatically without feeling it. Tiny increases compounded create massive results.","color":(20,80,40),"accent":(80,255,120),"lines":["THE 1% RULE","BUILDS WEALTH","SAVE 1% MORE","EVERY MONTH","MONTH 1: 10%","MONTH 12: 22%","YOU WON'T","FEEL IT"]},
  {"title":"Your Net Worth Is the Only Number That Matters","script":"Forget income. Forget salary. Net worth is the only number that predicts your financial future. Net worth is everything you own minus everything you owe. A doctor earning 300K with 500K in student debt has a lower net worth than a teacher with 200K in investments and no debt. Track your net worth monthly. Make it grow.","color":(60,0,100),"accent":(200,100,255),"lines":["NET WORTH","ONLY NUMBER","THAT MATTERS","ASSETS MINUS","LIABILITIES","DOCTOR $300K","SALARY BUT","NEGATIVE NET"]},
],
}

# ── Topic lists for AI script generation rotation ────────────────────────
TOPICS_PER_NICHE = {
    "personal_finance": [
        "hidden subscription fees draining your bank account",
        "emergency fund how much you really need",
        "compound interest explained with real numbers",
        "high yield savings accounts vs regular banks",
        "credit score hacks to boost 100 points fast",
        "budgeting method that actually works",
        "how to negotiate your salary for more money",
        "401k mistakes costing you thousands every year",
        "debt avalanche vs debt snowball method",
        "frugal living habits of millionaires",
        "side income that does not require a second job",
        "how inflation silently steals your purchasing power",
        "roth ira vs traditional ira which to pick",
        "hidden home ownership costs nobody tells you",
        "how to build 6 figure savings on average salary",
        "bank fees you should never be paying",
        "passive income strategies for under 1000 dollars",
        "money habits of people who retire early",
        "net worth calculation most people get wrong",
        "stock market basics every adult must know",
    ],
    "crypto": [
        "bitcoin halving and what it means for price",
        "ethereum staking passive income explained",
        "crypto tax mistakes that trigger IRS audits",
        "altcoins vs bitcoin risk comparison 2025",
        "cold wallet vs hot wallet security guide",
        "defi yield farming risk versus reward",
        "crypto portfolio diversification strategy",
        "how to buy crypto safely for beginners",
        "crypto scams destroying beginners portfolios",
        "bitcoin mining is it still profitable 2025",
        "layer 2 solutions making ethereum cheaper",
        "stablecoin risks most investors ignore",
        "dollar cost averaging into crypto explained",
        "crypto market cycles next bull run prediction",
        "web3 jobs that pay six figures",
        "crypto tax loss harvesting strategy",
        "decentralized vs centralized exchanges",
        "blockchain real world applications 2025",
        "nfts are they coming back in 2025",
        "best crypto under 1 dollar with potential",
    ],
    "real_estate": [
        "house hacking strategy to live rent free",
        "first time homebuyer mistakes to avoid",
        "rental property cash flow calculation",
        "real estate investing with under 10000 dollars",
        "REITs passive income without owning property",
        "airbnb versus long term rental comparison",
        "house flipping mistakes that cost beginners",
        "property tax reduction strategies that work",
        "how to find undervalued properties near you",
        "real estate depreciation tax benefits explained",
        "cap rate for beginners real estate investing",
        "1031 exchange explained simply",
        "commercial vs residential real estate returns",
        "how interest rates crush home buying power",
        "buy vs rent analysis 2025 real numbers",
        "seller financing creative real estate strategy",
        "building equity faster in your home",
        "real estate market crash warning signals",
        "rental income passive cash flow strategy",
        "short term rentals vs long term which wins",
    ],
    "side_hustle": [
        "freelancing on fiverr beginner success guide",
        "print on demand passive income 2025",
        "how to make 1000 dollars a month on etsy",
        "youtube channel monetization realistic timeline",
        "selling digital products that earn while you sleep",
        "amazon fba beginner profit margins reality",
        "affiliate marketing that actually pays in 2025",
        "social media management business from home",
        "AI tools to automate your side hustle income",
        "reselling thrift store finds for profit",
        "tutoring business startup guide no degree needed",
        "car detailing weekend side hustle income",
        "cleaning business profit margins explained",
        "newsletter business monetization strategy",
        "stock photography passive income stream",
        "bookkeeping side hustle no accounting degree",
        "dropshipping profitable niches this year",
        "voice acting gigs for beginners online",
        "lawn care business summer income guide",
        "virtual assistant 25 dollars per hour from home",
    ],
    "financeflow_promo": [
        "automated youtube channel with AI no recording",
        "AI tool that uploads finance videos automatically",
        "passive income youtube channel without effort",
        "how to post daily on youtube without recording",
        "finance youtube channel autopilot strategy",
    ],
}

def get_db():
    if _HAS_PG and DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
        conn.autocommit = False
        return conn
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def pg_execute(db, sql, params=()):
    """Execute SQL on both SQLite (db.execute) and PostgreSQL (cursor-based, %s placeholders)."""
    if _HAS_PG and DATABASE_URL:
        cur = db.cursor()
        sql = sql.replace("?", "%s")
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur
    else:
        if params:
            return db.execute(sql, params)
        else:
            return db.execute(sql)

# Keep _db_exec as alias for backwards compat
_db_exec = pg_execute

def _fetchone(db, sql, params=()):
    cur = pg_execute(db, sql, params)
    return cur.fetchone()

def _fetchall(db, sql, params=()):
    cur = pg_execute(db, sql, params)
    return cur.fetchall()

def refresh_yt_token(rt):
    print(f"   [TOKEN] Refreshing with client_id={CLIENT_ID[:20]}..." if CLIENT_ID else "   [TOKEN] WARNING: GOOGLE_CLIENT_ID is not set!")
    print(f"   [TOKEN] refresh_token present={bool(rt)} length={len(rt) if rt else 0}")
    data=urllib.parse.urlencode({"refresh_token":rt,"client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,"grant_type":"refresh_token"}).encode()
    req=urllib.request.Request("https://oauth2.googleapis.com/token",data=data,headers={"Content-Type":"application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as r:
            body=r.read()
            parsed=json.loads(body)
            if "access_token" not in parsed:
                print(f"   [TOKEN] ERROR: no access_token in response: {body.decode()[:300]}")
                raise Exception(f"No access_token in response: {body.decode()[:300]}")
            print("   [TOKEN] Refresh OK")
            return parsed["access_token"]
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8","replace")
        print(f"   [TOKEN] HTTP {e.code} error: {body[:500]}")
        raise Exception(f"Token refresh failed HTTP {e.code}: {body[:300]}")

def make_voice(text, out_wav, voice_id=None, rate=165):
    # Try ElevenLabs first if key is available
    if ELEVENLABS_KEY:
        try:
            vid = voice_id or ELEVENLABS_VOICE_ID
            payload = json.dumps({
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.55, "similarity_boost": 0.80, "style": 0.1, "use_speaker_boost": True}
            }).encode()
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                data=payload,
                headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json",
                         "Accept": "audio/mpeg"}
            )
            with urllib.request.urlopen(req) as r:
                mp3_data = r.read()
            mp3_path = out_wav.replace(".wav", ".mp3")
            with open(mp3_path, "wb") as f:
                f.write(mp3_data)
            if FFMPEG and os.path.exists(mp3_path):
                subprocess.run([FFMPEG, "-y", "-i", mp3_path, out_wav], capture_output=True)
                os.remove(mp3_path)
            if os.path.exists(out_wav):
                print("   ElevenLabs voice OK")
                return True
        except Exception as e:
            print(f"   ElevenLabs failed ({e}), trying OpenAI TTS...")
    # OpenAI TTS (high quality, uses OPENAI_API_KEY)
    if OPENAI_KEY:
        try:
            import openai as _oai
            _oai_client = _oai.OpenAI(api_key=OPENAI_KEY)
            response = _oai_client.audio.speech.create(
                model="tts-1-hd", voice="onyx", input=text, response_format="mp3"
            )
            mp3_path = out_wav.replace(".wav", "_oai.mp3")
            with open(mp3_path, "wb") as f:
                f.write(response.content)
            if FFMPEG and os.path.exists(mp3_path):
                subprocess.run([FFMPEG, "-y", "-i", mp3_path, out_wav], capture_output=True)
                os.remove(mp3_path)
            if os.path.exists(out_wav):
                print("   OpenAI TTS voice OK")
                return True
        except Exception as e:
            print(f"   OpenAI TTS failed ({e}), trying Edge TTS...")
    # Edge TTS (free, high quality, en-US-GuyNeural)
    try:
        import asyncio, edge_tts
        # Use provided voice_id if it looks like an Edge TTS voice name
        edge_voice = (voice_id if (voice_id and "Neural" in str(voice_id)) else "en-US-GuyNeural")
        async def _run_edge():
            communicate = edge_tts.Communicate(text, edge_voice)
            mp3_path = out_wav.replace(".wav", "_edge.mp3")
            await communicate.save(mp3_path)
            return mp3_path
        mp3_path = asyncio.run(_run_edge())
        if FFMPEG and os.path.exists(mp3_path):
            subprocess.run([FFMPEG, "-y", "-i", mp3_path, out_wav], capture_output=True)
            os.remove(mp3_path)
        if os.path.exists(out_wav):
            print("   Edge TTS voice OK")
            return True
    except Exception as e:
        print(f"   Edge TTS failed ({e}), trying gTTS...")
    # gTTS fallback
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang='en', slow=False)
        mp3_path = out_wav.replace(".wav", "_gtts.mp3")
        tts.save(mp3_path)
        if FFMPEG and os.path.exists(mp3_path):
            subprocess.run([FFMPEG, "-y", "-i", mp3_path, out_wav], capture_output=True)
            os.remove(mp3_path)
        if os.path.exists(out_wav):
            print("   gTTS voice OK")
            return True
    except Exception as e:
        print(f"   gTTS failed ({e})")
    # Last resort: Mac say (local dev only)
    try:
        aiff = out_wav.replace(".wav", ".aiff")
        for voice in ["Daniel", "Samantha", "Alex", "Karen", "Tom"]:
            res = subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", aiff, "--", text],
                                 capture_output=True)
            if res.returncode == 0 and os.path.exists(aiff):
                break
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", aiff, out_wav],
                       capture_output=True)
        if os.path.exists(aiff):
            os.remove(aiff)
        if os.path.exists(out_wav):
            return True
    except Exception:
        pass
    return False

def get_duration(wav):
    try:
        with wave.open(wav) as w: return w.getnframes()/w.getframerate()
    except: return 45.0

def make_music(out, dur=60):
    """Generate motivational background music with proper chord progression and stereo mix."""
    sr = 44100
    # I-V-vi-IV progression in C major (440Hz tuning)
    # Each chord is [root, third, fifth, octave]
    chord_freqs = [
        [261.63, 329.63, 392.00, 523.25],   # C major
        [392.00, 493.88, 587.33, 784.00],   # G major
        [220.00, 261.63, 329.63, 440.00],   # A minor
        [349.23, 440.00, 523.25, 698.46],   # F major
    ]
    bass_notes  = [130.81, 196.00, 110.00, 174.61]  # bass octave
    beat_period = 60.0 / 120  # 120 BPM
    chord_dur   = 2.0  # 2 seconds per chord

    frames_l = []
    frames_r = []
    total_samples = sr * int(dur + 2)

    for i in range(total_samples):
        t = i / sr
        ci = int(t / chord_dur) % len(chord_freqs)
        chord = chord_freqs[ci]
        pos_in_chord = (t % chord_dur) / chord_dur

        # Master volume fade in/out
        master = min(t / 0.8, 1.0, (dur - t) / 0.8)

        # Chord envelope (soft attack, sustain, slight release at end of chord)
        env = min(pos_in_chord / 0.06, 1.0, 1.0 - max(0, pos_in_chord - 0.85) / 0.15)

        # Pad sound: 4-voice chord with slight detuning for width
        pad_l = sum(0.07 * math.sin(2 * math.pi * f * t * (1 + 0.001 * (j % 2 == 0 and 1 or -1)))
                    for j, f in enumerate(chord))
        pad_r = sum(0.07 * math.sin(2 * math.pi * f * t * (1 + 0.001 * (j % 2 == 1 and 1 or -1)))
                    for j, f in enumerate(chord))

        # Bass: root + octave, punchy
        bass_f = bass_notes[ci]
        bass_env = min(pos_in_chord / 0.02, 1.0) * math.exp(-pos_in_chord * 2.5)
        bass = 0.18 * math.sin(2 * math.pi * bass_f * t) * bass_env
        bass += 0.06 * math.sin(2 * math.pi * bass_f * 2 * t) * bass_env

        # Kick drum (4 on the floor)
        beat_pos = (t / beat_period) % 1.0
        kick_env = math.exp(-beat_pos * 18) if beat_pos < 0.25 else 0
        kick_freq = 55 + 180 * math.exp(-beat_pos * 30)
        kick = 0.22 * math.sin(2 * math.pi * kick_freq * t) * kick_env

        # Snare on beats 2 and 4
        snare_beat = (t / beat_period + 0.5) % 1.0  # offset by half beat
        snare_on = (int(t / beat_period) % 2 == 1)
        snare_env = math.exp(-snare_beat * 22) if snare_beat < 0.15 and snare_on else 0
        snare = snare_env * (0.08 * random.gauss(0, 1) + 0.04 * math.sin(2 * math.pi * 200 * t))

        # Hi-hat (8th notes)
        hh_beat = (t / (beat_period / 2)) % 1.0
        hh_env = math.exp(-hh_beat * 30) if hh_beat < 0.12 else 0
        hh = 0.025 * random.gauss(0, 1) * hh_env

        # Mix (pad stereo, drums mono center)
        drums = kick + snare + hh
        left  = (pad_l * env + bass + drums) * master
        right = (pad_r * env + bass + drums) * master

        # Soft clip / limiter
        def clip(x):
            return math.tanh(x * 1.4) * 0.72

        frames_l.append(struct.pack('<h', max(-32767, min(32767, int(clip(left) * 28000)))))
        frames_r.append(struct.pack('<h', max(-32767, min(32767, int(clip(right) * 28000)))))

    # Interleave stereo samples L R L R
    interleaved = b''.join(l + r for l, r in zip(frames_l, frames_r))
    with wave.open(out, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(interleaved)

def _draw_rounded_rect(draw, xy, radius, fill, outline=None, outline_width=2):
    """Draw a rounded rectangle using PIL primitives."""
    x0, y0, x1, y1 = xy
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse([x1 - 2*r, y0, x1, y0 + 2*r], fill=fill)
    draw.ellipse([x0, y1 - 2*r, x0 + 2*r, y1], fill=fill)
    draw.ellipse([x1 - 2*r, y1 - 2*r, x1, y1], fill=fill)
    if outline:
        draw.arc([x0, y0, x0 + 2*r, y0 + 2*r], 180, 270, fill=outline, width=outline_width)
        draw.arc([x1 - 2*r, y0, x1, y0 + 2*r], 270, 360, fill=outline, width=outline_width)
        draw.arc([x0, y1 - 2*r, x0 + 2*r, y1], 90, 180, fill=outline, width=outline_width)
        draw.arc([x1 - 2*r, y1 - 2*r, x1, y1], 0, 90, fill=outline, width=outline_width)
        draw.line([x0 + r, y0, x1 - r, y0], fill=outline, width=outline_width)
        draw.line([x0 + r, y1, x1 - r, y1], fill=outline, width=outline_width)
        draw.line([x0, y0 + r, x0, y1 - r], fill=outline, width=outline_width)
        draw.line([x1, y0 + r, x1, y1 - r], fill=outline, width=outline_width)


def _gradient_rect(img, x0, y0, x1, y1, color_top, color_bot):
    """Draw a vertical gradient rectangle directly onto image pixels."""
    draw = ImageDraw.Draw(img)
    h = y1 - y0
    for dy in range(h):
        ratio = dy / max(h - 1, 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * ratio)
        draw.line([(x0, y0 + dy), (x1, y0 + dy)], fill=(
            max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))


def make_frames(sd, dur, fdir, vtype, bg_path=None):
    from PIL import ImageFilter
    os.makedirs(fdir, exist_ok=True)
    W, H = (540, 960) if vtype == "short" else (960, 540)
    FPS = 24
    c, a = sd["color"], sd["accent"]
    lines = sd["lines"]
    niche = sd.get("niche", "personal_finance")
    theme = NICHE_THEMES.get(niche, {"bg": (8, 8, 8), "bg2": (25, 18, 4), "grid": (35, 28, 8)})

    nf = int(dur * FPS)
    MAX_FRAMES = 240  # 10s at 24fps = 240 frames max
    step = max(1, nf // MAX_FRAMES) if nf > MAX_FRAMES else 1
    frame_indices = list(range(0, nf, step))[:MAX_FRAMES]
    actual_nf = len(frame_indices)
    if nf > MAX_FRAMES:
        print(f"   [FRAMES] Sampling {nf} → {actual_nf} frames (step={step})")

    # Pre-build base background (gradient + vignette) once and reuse
    bg_base = Image.new("RGB", (W, H))
    # Rich gradient: top slightly lighter, bottom darker
    bg2 = theme["bg2"]
    _gradient_rect(bg_base, 0, 0, W, H,
                   (max(0, c[0] + 15), max(0, c[1] + 10), max(0, c[2] + 20)),
                   (max(0, bg2[0] - 5), max(0, bg2[1] - 5), max(0, bg2[2] - 5)))

    # Vignette overlay (dark edges, lighter center)
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    cx, cy = W // 2, H // 2
    for radius in range(max(W, H), 0, -8):
        alpha = int(min(255, (radius / max(W, H)) * 200))
        vd.ellipse([cx - radius, cy - radius * H // W,
                    cx + radius, cy + radius * H // W], fill=alpha)
    vig_overlay = Image.new("RGB", (W, H), (0, 0, 0))
    bg_base = Image.composite(bg_base, vig_overlay, vignette)

    # Load external background if provided
    bg_img = None
    if bg_path and os.path.exists(bg_path):
        try:
            raw = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
            dark = Image.new("RGB", (W, H), (0, 0, 0))
            bg_img = Image.blend(raw, dark, 0.55)
            print(f"   [FRAMES] AI background: {bg_path}")
        except Exception as e:
            print(f"   [FRAMES] BG load failed ({e}), using gradient")

    # Subtle dot pattern overlay
    dot_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dot_overlay)
    gc = theme["grid"]
    dot_col = (gc[0], gc[1], gc[2], 55)
    for gx in range(0, W, 40):
        for gy in range(0, H, 40):
            dd.ellipse([gx - 1, gy - 1, gx + 1, gy + 1], fill=dot_col)

    # Build sparkline data — niche-specific realistic chart patterns
    n_points = 20
    rng_seed = sum(ord(c) for c in (sd.get("title", "") or niche))
    _rng = random.Random(rng_seed)  # deterministic per video

    if niche in ("crypto",):
        # Volatile: large swings, overall uptrend with a correction dip
        base = [_rng.gauss(0, 0.18) for _ in range(n_points)]
        trend = [i * 0.04 for i in range(n_points)]
        dip_start = int(n_points * 0.55)
        dip = [max(0, 0.4 * math.exp(-0.6 * abs(i - dip_start))) for i in range(n_points)]
        spark_vals = [0.3 + b + t - d for b, t, d in zip(base, trend, dip)]
    elif niche in ("real_estate",):
        # Slow steady climb with minor bumps
        spark_vals = [0.35 + i * 0.032 + _rng.gauss(0, 0.04) for i in range(n_points)]
    elif niche in ("side_hustle",):
        # Hockey stick: flat then rapid growth
        spark_vals = [0.2 + _rng.gauss(0, 0.03) if i < n_points * 0.6
                      else 0.25 + (i - n_points * 0.6) * 0.09 + _rng.gauss(0, 0.04)
                      for i in range(n_points)]
    else:
        # Personal finance / investing: compound growth curve + small noise
        spark_vals = [0.2 + 0.7 * (1 - math.exp(-i * 0.18)) + _rng.gauss(0, 0.025)
                      for i in range(n_points)]

    # Normalize to [0.05, 0.95]
    sv_min, sv_max = min(spark_vals), max(spark_vals)
    sv_range = sv_max - sv_min if sv_max != sv_min else 1
    spark_vals = [0.05 + 0.90 * (v - sv_min) / sv_range for v in spark_vals]

    cd = dur / max(len(lines), 1)

    for out_idx, f in enumerate(frame_indices):
        t = f / FPS
        li = min(int(t / cd), len(lines) - 1)

        # Base frame
        if bg_img:
            img = bg_img.copy().convert("RGBA")
        else:
            img = bg_base.copy().convert("RGBA")

        # Apply dot overlay
        img = Image.alpha_composite(img, dot_overlay)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── Top bar ──────────────────────────────────────────────────────
        # Gradient accent bar at top (4px solid + fade)
        draw.rectangle([0, 0, W, 4], fill=a)
        for dy in range(5, 18):
            alpha = int(255 * (1 - (dy - 4) / 14))
            r = int(a[0] * alpha / 255)
            g = int(a[1] * alpha / 255)
            b = int(a[2] * alpha / 255)
            draw.line([(0, dy), (W, dy)], fill=(r, g, b))

        # ── Niche pill label ─────────────────────────────────────────────
        label = NICHE_LABELS.get(niche, "FINANCE CHANNEL")
        pill_w = len(label) * 9 + 32
        pill_x = W // 2 - pill_w // 2
        _draw_rounded_rect(draw, [pill_x, 26, pill_x + pill_w, 56], 14,
                           fill=(int(a[0] * 0.2), int(a[1] * 0.2), int(a[2] * 0.2)),
                           outline=(*a, ), outline_width=1)
        draw.text((W // 2, 41), label, fill=a, font=fnt(20), anchor="mm")

        # ── Animated sparkline chart ─────────────────────────────────────
        chart_h = int(H * 0.10)
        chart_y = int(H * 0.80)
        chart_x0 = int(W * 0.08)
        chart_x1 = int(W * 0.92)
        chart_w = chart_x1 - chart_x0
        # Animated reveal: chart draws in from left over first 2s
        reveal = min(1.0, t / 2.5)
        pts_to_show = max(2, int(n_points * reveal))
        pts = []
        for i in range(pts_to_show):
            px = chart_x0 + int(i * chart_w / (n_points - 1))
            py = chart_y + chart_h - int(spark_vals[i] * chart_h)
            # Subtle pulse on last visible point
            if i == pts_to_show - 1:
                pulse = math.sin(t * 8) * 3
                py = int(py + pulse)
            pts.append((px, py))
        if len(pts) >= 2:
            # Area fill under the line (semi-transparent)
            chart_bottom = chart_y + chart_h + 4
            fill_poly = pts + [(pts[-1][0], chart_bottom), (pts[0][0], chart_bottom)]
            fill_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            fill_draw = ImageDraw.Draw(fill_overlay)
            fill_draw.polygon(fill_poly, fill=(*a, 28))
            img = Image.alpha_composite(img.convert("RGBA"), fill_overlay).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Gradient line effect (glow + main line)
            glow = (min(255, a[0] + 40), min(255, a[1] + 40), min(255, a[2] + 40))
            for dx_off, lw, col in [(-1, 4, (*a, 55)), (0, 2, a), (0, 1, glow)]:
                off_pts = [(x + dx_off, y) for x, y in pts]
                if len(off_pts) >= 2:
                    draw.line(off_pts, fill=col if len(col) == 3 else col[:3], width=lw)
            # Dot at latest point with outer ring
            lx, ly = pts[-1]
            dot_r = 6
            draw.ellipse([lx - dot_r - 2, ly - dot_r - 2, lx + dot_r + 2, ly + dot_r + 2],
                         fill=(*a, 60) if len(a) == 3 else a)
            draw.ellipse([lx - dot_r, ly - dot_r, lx + dot_r, ly + dot_r], fill=a)
            draw.ellipse([lx - 2, ly - 2, lx + 2, ly + 2], fill=(255, 255, 255))

        # ── Main text card ───────────────────────────────────────────────
        line = lines[li] if li < len(lines) else ""
        # Ease in: slide up from below + fade
        line_start_t = li * cd
        line_age = t - line_start_t
        ease = min(1.0, line_age / 0.18)  # 0.18s ease
        y_offset = int((1 - ease) * 35)
        text_alpha = int(ease * 255)

        # Font size: shorter lines get bigger text
        base_sz = 90 if vtype == "short" else 72
        if len(line) > 10:
            base_sz = int(base_sz * 0.85)
        if len(line) > 16:
            base_sz = int(base_sz * 0.78)
        tsz = base_sz

        # Text position: center vertically in the content zone
        content_cy = H // 2 - (30 if vtype == "short" else 20)
        text_y = content_cy + y_offset

        if text_alpha > 10:
            # Multi-layer text: outer glow → shadow → main
            glow_sz = max(1, tsz // 20)
            for off in [(glow_sz * 2, glow_sz * 2), (-glow_sz, glow_sz), (0, glow_sz * 2)]:
                draw.text((W // 2 + off[0], text_y + off[1]), line,
                          fill=(0, 0, 0), font=fnt(tsz), anchor="mm")
            # Accent glow
            draw.text((W // 2, text_y), line,
                      fill=(min(255, a[0] + 30), min(255, a[1] + 30), min(255, a[2] + 30)),
                      font=fnt(tsz), anchor="mm")
            # Main text (white or accent depending on brightness)
            brightness = (a[0] * 299 + a[1] * 587 + a[2] * 114) // 1000
            text_col = (255, 255, 255) if brightness < 180 else a
            draw.text((W // 2, text_y), line, fill=text_col, font=fnt(tsz), anchor="mm")

        # Underline accent
        try:
            bbox = fnt(tsz).getbbox(line)
            text_w = bbox[2] - bbox[0] if bbox else W // 2
        except Exception:
            text_w = W // 2
        ul_w = min(text_w + 20, W - 80)
        ul_y = text_y + tsz // 2 + 8
        draw.rectangle([W // 2 - ul_w // 2, ul_y, W // 2 + ul_w // 2, ul_y + 2], fill=a)

        # Line counter dots (shows progress through lines)
        dot_row_y = int(H * 0.89)
        dot_spacing = 14
        n_dots = len(lines)
        dots_x0 = W // 2 - (n_dots * dot_spacing) // 2
        for di in range(n_dots):
            dx = dots_x0 + di * dot_spacing + dot_spacing // 2
            if di == li:
                draw.ellipse([dx - 4, dot_row_y - 4, dx + 4, dot_row_y + 4], fill=a)
            else:
                draw.ellipse([dx - 2, dot_row_y - 2, dx + 2, dot_row_y + 2],
                             fill=(int(a[0] * 0.35), int(a[1] * 0.35), int(a[2] * 0.35)))

        # ── Bottom bar ───────────────────────────────────────────────────
        draw.rectangle([0, H - 4, W, H], fill=a)
        # Progress bar
        prog = int((t / dur) * (W - 60))
        draw.rectangle([30, H - 8, 30 + max(prog, 4), H - 5],
                       fill=(int(a[0] * 0.6), int(a[1] * 0.6), int(a[2] * 0.6)))

        # Watermark
        draw.text((W // 2, H - 18), "FinanceFlow AI", fill=(80, 80, 80), font=fnt(14), anchor="mm")

        # ── Fade in / out ────────────────────────────────────────────────
        fade_frames = int(FPS * 0.25)
        if f < fade_frames:
            alpha = f / fade_frames
            dk = Image.new("RGB", (W, H), (0, 0, 0))
            img = Image.blend(dk, img, alpha)
        elif f > nf - fade_frames:
            alpha = max(0.0, (nf - f) / fade_frames)
            dk = Image.new("RGB", (W, H), (0, 0, 0))
            img = Image.blend(dk, img, alpha)

        # ── End card (last 2.5s) ─────────────────────────────────────────
        end_frames = int(FPS * 2.5)
        if out_idx >= actual_nf - end_frames:
            ec_progress = (out_idx - (actual_nf - end_frames)) / max(1, end_frames)
            ec_alpha = min(1.0, ec_progress / 0.3)
            ec = Image.new("RGB", (W, H), (6, 6, 10))
            ecd = ImageDraw.Draw(ec)
            # Top accent
            ecd.rectangle([0, 0, W, 4], fill=a)
            # Logo glow
            ecd.text((W // 2, H // 2 - 45), "FinanceFlow", fill=a, font=fnt(56), anchor="mm")
            ecd.text((W // 2, H // 2 + 18), "AI · automate your channel", fill=(130, 130, 130), font=fnt(22), anchor="mm")
            ecd.rectangle([W // 2 - 60, H // 2 + 48, W // 2 + 60, H // 2 + 50], fill=a)
            img = Image.blend(img, ec, ec_alpha)

        img.save(f"{fdir}/f{out_idx:06d}.jpg", quality=88)

    return FPS

def make_thumb(sd, out, vtype):
    W, H = (1080, 1920) if vtype == "short" else (1280, 720)
    c, a = sd["color"], sd["accent"]
    title_text = sd.get("title", "")[:55]
    niche = sd.get("niche", "personal_finance")

    # Rich gradient background
    img = Image.new("RGB", (W, H))
    _gradient_rect(img, 0, 0, W, H,
                   (max(0, c[0] + 20), max(0, c[1] + 12), max(0, c[2] + 28)),
                   (max(0, c[0] - 10), max(0, c[1] - 8), max(0, c[2] - 12)))

    draw = ImageDraw.Draw(img)

    # Diagonal accent stripe
    poly = [(0, 0), (W // 3, 0), (0, H // 4)]
    draw.polygon(poly, fill=(int(a[0] * 0.25), int(a[1] * 0.25), int(a[2] * 0.25)))

    # Top bar
    draw.rectangle([0, 0, W, 12], fill=a)

    # Channel label pill
    label = NICHE_LABELS.get(niche, "FINANCE")
    lw = len(label) * 18 + 48
    lx = W // 2 - lw // 2
    ly_top = H // 4 - 30 if vtype == "short" else 60
    _draw_rounded_rect(draw, [lx, ly_top, lx + lw, ly_top + 52], 26,
                       fill=(int(a[0] * 0.25), int(a[1] * 0.25), int(a[2] * 0.25)),
                       outline=a, outline_width=2)
    draw.text((W // 2, ly_top + 26), label, fill=a, font=fnt(26), anchor="mm")

    # Title text with word wrap
    words = title_text.split()
    lines_out = []
    cur = ""
    max_chars = 18 if vtype == "short" else 28
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines_out.append(cur)
            cur = w
    if cur:
        lines_out.append(cur)
    lines_out = lines_out[:4]

    tsz = 110 if vtype == "short" else 96
    if len(lines_out) > 2:
        tsz = int(tsz * 0.82)

    cy = H // 2
    line_h = tsz + 12
    start_y = cy - (len(lines_out) * line_h) // 2

    for i, ln in enumerate(lines_out):
        ty = start_y + i * line_h
        # Shadow layers
        for off in [(4, 4), (2, 3), (1, 1)]:
            draw.text((W // 2 + off[0], ty + off[1]), ln,
                      fill=(0, 0, 0), font=fnt(tsz), anchor="mm")
        brightness = (a[0] * 299 + a[1] * 587 + a[2] * 114) // 1000
        text_col = (255, 255, 255) if brightness < 160 else a
        draw.text((W // 2, ty), ln, fill=text_col, font=fnt(tsz), anchor="mm")

    # Small decorative sparkline above CTA bar
    spark_seed = sum(ord(ch) for ch in title_text[:10])
    _rng_t = random.Random(spark_seed)
    sp_n = 12
    if niche == "crypto":
        sp_vals = [0.3 + _rng_t.gauss(0, 0.15) + i * 0.04 for i in range(sp_n)]
    elif niche == "real_estate":
        sp_vals = [0.2 + i * 0.055 + _rng_t.gauss(0, 0.02) for i in range(sp_n)]
    else:
        sp_vals = [0.2 + 0.7 * (1 - math.exp(-i * 0.3)) + _rng_t.gauss(0, 0.02) for i in range(sp_n)]
    sp_min, sp_max = min(sp_vals), max(sp_vals)
    sp_range = sp_max - sp_min if sp_max != sp_min else 1
    sp_vals = [0.1 + 0.8 * (v - sp_min) / sp_range for v in sp_vals]
    sp_h = 44 if vtype == "short" else 36
    sp_y = H - 110 if vtype == "short" else H - 100
    sp_x0, sp_x1 = int(W * 0.1), int(W * 0.9)
    sp_w = sp_x1 - sp_x0
    sp_pts = [(sp_x0 + int(i * sp_w / (sp_n - 1)), sp_y + sp_h - int(v * sp_h))
              for i, v in enumerate(sp_vals)]
    if len(sp_pts) >= 2:
        draw.line(sp_pts, fill=(*a, 120) if len(a) == 3 else a, width=3)
        lx2, ly2 = sp_pts[-1]
        draw.ellipse([lx2 - 4, ly2 - 4, lx2 + 4, ly2 + 4], fill=a)

    # Subscribe CTA bar at bottom
    draw.rectangle([0, H - 80, W, H], fill=(0, 0, 0))
    draw.rectangle([0, H - 80, W, H - 76], fill=a)
    draw.text((W // 2, H - 40), "SUBSCRIBE  ·  NEW VIDEOS DAILY",
              fill=(200, 200, 200), font=fnt(28), anchor="mm")
    draw.text((W // 2, H - 12), "FinanceFlow AI", fill=(80, 80, 80), font=fnt(18), anchor="mm")

    img.save(out, quality=95)

def render_video(fdir,audio,out,fps):
    all_frames = sorted([f for f in os.listdir(fdir) if f.endswith(".jpg")]) if os.path.isdir(fdir) else []
    frame_count = len(all_frames)
    audio_size  = os.path.getsize(audio) if os.path.exists(audio) else 0
    print(f"   [RENDER] ffmpeg={FFMPEG} frames={frame_count} audio={audio_size}B fps={fps}")

    # If too many frames (shouldn't happen after make_frames cap, but safety net)
    if frame_count > 150:
        step = frame_count // 150
        keep = all_frames[::step][:150]
        remove = set(all_frames) - set(keep)
        for fn in remove:
            try: os.remove(f"{fdir}/{fn}")
            except: pass
        for i, fn in enumerate(sorted(keep)):
            src = f"{fdir}/{fn}"
            dst = f"{fdir}/f{i:06d}.jpg"
            if src != dst:
                os.rename(src, dst)
        frame_count = len(keep)
        print(f"   [RENDER] Safety-thinned to {frame_count} frames")

    if FFMPEG:
        cmd=[FFMPEG,"-y","-threads","2","-framerate",str(fps),"-i",f"{fdir}/f%06d.jpg","-i",audio,
             "-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p",
             "-c:a","aac","-b:a","192k","-af","loudnorm=I=-16:LRA=11:TP=-1.5",
             "-shortest","-movflags","+faststart",out]
        print(f"   [RENDER] Running: {' '.join(cmd)}")
        r=subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(f"   [RENDER] ffmpeg={FFMPEG} exited {r.returncode}")
            print(f"   [RENDER] stderr: {r.stderr.decode('utf-8','replace')[-800:]}")
        elif os.path.exists(out):
            size=os.path.getsize(out)
            if size == 0:
                print("   [RENDER] ffmpeg produced 0-byte file")
                os.remove(out)
            else:
                print(f"   [RENDER] ffmpeg OK — {size/1024/1024:.2f}MB")
                return True

    # moviepy fallback
    print("   [RENDER] Trying moviepy fallback...")
    try:
        try:
            from moviepy.editor import ImageSequenceClip, AudioFileClip
        except ImportError:
            try:
                from moviepy import ImageSequenceClip, AudioFileClip
            except ImportError:
                ImageSequenceClip = None
        if not ImageSequenceClip:
            print("   [RENDER] moviepy not available")
            return False
        frames = sorted([f"{fdir}/{fn}" for fn in os.listdir(fdir) if fn.endswith(".jpg")])
        print(f"   [RENDER] moviepy: {len(frames)} frames")
        clip = ImageSequenceClip(frames, fps=12)
        aclip = AudioFileClip(audio)
        clip = clip.set_audio(aclip)
        clip.write_videofile(out, codec="libx264", audio_codec="aac", logger=None,
                             ffmpeg_params=["-preset","ultrafast","-crf","23","-threads","1"])
        if os.path.exists(out):
            size=os.path.getsize(out)
            if size == 0:
                print("   [RENDER] moviepy produced 0-byte file")
                os.remove(out)
                return False
            print(f"   [RENDER] moviepy OK — {size/1024/1024:.2f}MB")
            return True
        return False
    except Exception as e:
        print(f"   [RENDER] moviepy failed: {e}")
        import traceback; traceback.print_exc()
        return False

def upload_youtube(token,mp4,title,desc,tags):
    print(f"   [UPLOAD] token={token[:20]}... file={mp4} size={os.path.getsize(mp4)/1024/1024:.2f}MB")
    fs=os.path.getsize(mp4)
    meta=json.dumps({"snippet":{"title":title[:100],"description":desc[:4990],"tags":[t[:30] for t in tags[:15]],"categoryId":"22","defaultLanguage":"en"},"status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}).encode()
    try:
        init=urllib.request.Request("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",data=meta,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json; charset=UTF-8","X-Upload-Content-Type":"video/mp4","X-Upload-Content-Length":str(fs)})
        with urllib.request.urlopen(init) as r: up_url=r.headers["Location"]
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8","replace")
        print(f"   [UPLOAD] Init HTTP {e.code}: {body[:300]}")
        raise Exception(f"Upload init failed HTTP {e.code}: {body[:200]}")
    chunk=5*1024*1024; uploaded=0; vid_id=None
    with open(mp4,"rb") as f:
        while uploaded<fs:
            data=f.read(chunk)
            if not data: break
            end=uploaded+len(data)-1
            req=urllib.request.Request(up_url,data=data,headers={"Content-Type":"video/mp4","Content-Range":f"bytes {uploaded}-{end}/{fs}"},method="PUT")
            try:
                with urllib.request.urlopen(req) as r:
                    if r.status in (200,201): vid_id=json.loads(r.read()).get("id")
            except urllib.error.HTTPError as e:
                if e.code!=308: raise
            uploaded+=len(data)
            print(f"\r   Upload: {int(uploaded/fs*100)}%",end="",flush=True)
    print(); return vid_id

def upload_thumb(token,vid_id,thumb_path):
    try:
        with open(thumb_path,"rb") as f: td=f.read()
        urllib.request.urlopen(urllib.request.Request(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}&uploadType=media",data=td,headers={"Authorization":f"Bearer {token}","Content-Type":"image/jpeg"}))
        return True
    except: return False

# ── SOCIAL MEDIA POSTING ──────────────────────────────────────

def oauth1_header(method,url,body_params,api_key,api_secret,token,token_secret):
    nonce=secrets.token_hex(16); ts=str(int(time.time()))
    oauth={"oauth_consumer_key":api_key,"oauth_nonce":nonce,"oauth_signature_method":"HMAC-SHA1","oauth_timestamp":ts,"oauth_token":token,"oauth_version":"1.0"}
    all_params={**oauth,**body_params}
    base_str="&".join([urllib.parse.quote(method,""),urllib.parse.quote(url,""),urllib.parse.quote("&".join(f"{urllib.parse.quote(str(k),'')  }={urllib.parse.quote(str(v),'')}" for k,v in sorted(all_params.items())),"") ])
    sign_key=f"{urllib.parse.quote(api_secret,'')}&{urllib.parse.quote(token_secret,'')}"
    sig=base64.b64encode(hmac.new(sign_key.encode(),base_str.encode(),hashlib.sha1).digest()).decode()
    oauth["oauth_signature"]=sig
    return "OAuth "+(", ".join(f'{urllib.parse.quote(k,"")}="{urllib.parse.quote(v,"")}"' for k,v in sorted(oauth.items())))

def post_twitter(creds,youtube_url,title,niche):
    try:
        api_key=creds.get("api_key",""); api_secret=creds.get("api_secret",""); token=creds.get("access_token",""); t_secret=creds.get("access_secret","")
        if not all([api_key,api_secret,token,t_secret]): return None,"Missing Twitter API credentials"
        ht={"personal_finance":"#personalfinance #money #finance","crypto":"#crypto #bitcoin","real_estate":"#realestate #investing","side_hustle":"#sidehustle #makemoney"}.get(niche,"#finance")
        text=f"{title}\n\n{ht}\n\nWatch: {youtube_url}"[:280]
        url="https://api.twitter.com/2/tweets"; body=json.dumps({"text":text}).encode()
        auth=oauth1_header("POST",url,{},api_key,api_secret,token,t_secret)
        req=urllib.request.Request(url,data=body,headers={"Authorization":auth,"Content-Type":"application/json"})
        with urllib.request.urlopen(req) as r: result=json.loads(r.read())
        tid=result.get("data",{}).get("id","")
        return f"https://twitter.com/i/web/status/{tid}",None
    except Exception as e: return None,str(e)

def post_facebook(creds,youtube_url,title,niche):
    try:
        page_id=creds.get("page_id",""); page_token=creds.get("page_token","")
        if not page_id or not page_token: return None,"Missing Facebook Page ID or Token"
        ht={"personal_finance":"#personalfinance #money","crypto":"#crypto #bitcoin","real_estate":"#realestate","side_hustle":"#sidehustle"}.get(niche,"#finance")
        message=f"{title}\n\n{ht}\n\nWatch: {youtube_url}"
        data=urllib.parse.urlencode({"message":message,"link":youtube_url,"access_token":page_token}).encode()
        with urllib.request.urlopen(urllib.request.Request(f"https://graph.facebook.com/v19.0/{page_id}/feed",data=data)) as r:
            result=json.loads(r.read())
        post_id=result.get("id","")
        return f"https://facebook.com/{post_id}",None
    except Exception as e: return None,str(e)

def post_instagram(creds,youtube_url,title,thumb_path):
    return None,"Instagram requires public video URL — deploy your app first"

def post_tiktok(creds,youtube_url,title):
    return None,"TikTok requires approved developer account at developers.tiktok.com"

def cross_post_social(channel_id,video_id,youtube_url,title,niche,thumb_path):
    db=get_db()
    accounts=_fetchall(db, "SELECT * FROM social_accounts WHERE channel_id=? AND active=1",(channel_id,))
    db.close()
    for acc in accounts:
        platform=acc["platform"]; creds=json.loads(acc["credentials"])
        post_url,err=None,"Not implemented"
        print(f"   📱 Posting to {platform.title()}...")
        try:
            if platform=="twitter": post_url,err=post_twitter(creds,youtube_url,title,niche)
            elif platform=="facebook": post_url,err=post_facebook(creds,youtube_url,title,niche)
            elif platform=="instagram": post_url,err=post_instagram(creds,youtube_url,title,thumb_path)
            elif platform=="tiktok": post_url,err=post_tiktok(creds,youtube_url,title)
            status="posted" if post_url else "failed"
            print(f"   {'OK' if post_url else 'SKIP'} {platform.title()}: {post_url or err}")
        except Exception as e:
            status="failed"; err=str(e)[:200]
        db=get_db()
        pg_execute(db, "INSERT INTO social_posts (video_id,channel_id,platform,post_url,status,error_msg) VALUES (?,?,?,?,?,?)",(video_id,channel_id,platform,post_url,status,err))
        db.commit(); db.close()

_BG_CACHE_DIR = _HERE / "bg_cache"

def get_ai_background(topic, vtype):
    """Download background image from Pollinations.ai. Returns path or None."""
    import hashlib
    _BG_CACHE_DIR.mkdir(exist_ok=True)
    W, H = (540, 960) if vtype == "short" else (960, 540)
    topic_slug = urllib.parse.quote(topic.replace(" ", "+")[:60])
    url = f"https://image.pollinations.ai/prompt/dark+finance+{topic_slug}+professional+cinematic?width={W}&height={H}&nologo=true"
    cache_key = hashlib.md5(url.encode()).hexdigest()[:12]
    cache_path = _BG_CACHE_DIR / f"{cache_key}.jpg"
    if cache_path.exists():
        print(f"   [BG] Cache hit")
        return str(cache_path)
    try:
        print(f"   [BG] Downloading Pollinations background...")
        req = urllib.request.Request(url, headers={"User-Agent": "FinanceFlow/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 5000:
            print(f"   [BG] Response too small ({len(data)}B), skipping")
            return None
        with open(cache_path, "wb") as f:
            f.write(data)
        print(f"   [BG] Downloaded {len(data)//1024}KB")
        return str(cache_path)
    except Exception as e:
        print(f"   [BG] Download failed ({e}), using gradient")
        return None

def ai_generate_script(topic, niche):
    """Use GPT-4o-mini to generate a unique script + title + tags."""
    if not OPENAI_KEY:
        return None
    try:
        import openai as _oai
        client = _oai.OpenAI(api_key=OPENAI_KEY)
        script_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content":
                f"Write a 45-second YouTube Shorts script about '{topic}' for a finance channel. "
                "Make it shocking, urgent, valuable. Start with a hook. Include specific numbers. "
                "End with a CTA to subscribe. Spoken words only. No stage directions. No headers."}],
            max_tokens=320, temperature=0.9,
        )
        script_text = script_resp.choices[0].message.content.strip()
        meta_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content":
                f"For a YouTube Shorts finance video about '{topic}', provide:\n"
                "TITLE: (under 70 chars, shocking/urgent)\n"
                "TAGS: (10 comma-separated tags, no #)"}],
            max_tokens=120, temperature=0.7,
        )
        meta = meta_resp.choices[0].message.content.strip()
        title, tags = "", []
        for line in meta.split("\n"):
            if line.upper().startswith("TITLE:"):
                title = line[6:].strip()
            elif line.upper().startswith("TAGS:"):
                tags = [t.strip().lower() for t in line[5:].split(",") if t.strip()]
        print(f"   [AI] GPT-4o-mini script: '{title[:50]}' ({len(script_text)} chars)")
        return {"script": script_text, "title": title or topic.title(), "tags": tags}
    except Exception as e:
        print(f"   [AI] GPT-4o-mini failed ({e}), using built-in library")
        return None

def get_next_topic(niche, channel_id):
    """Pick a topic from TOPICS_PER_NICHE, avoiding the last 10 used."""
    topics = TOPICS_PER_NICHE.get(niche, TOPICS_PER_NICHE["personal_finance"])
    try:
        db = get_db()
        recent = _fetchall(db, "SELECT title FROM videos WHERE channel_id=? ORDER BY created_at DESC LIMIT 10", (channel_id,))
        db.close()
        used = [r["title"].lower() for r in recent]
    except Exception:
        used = []
    available = [t for t in topics if not any(
        any(w in u for w in t.lower().split()[:3]) for u in used
    )]
    return random.choice(available if available else topics)

def _build_sd_from_ai(ai_result, topic, niche, ctitle):
    """Build an sd dict from an AI-generated script result."""
    colors  = {"personal_finance":(160,15,15),"crypto":(160,70,0),"real_estate":(15,55,15),"side_hustle":(0,55,110)}
    accents = {"personal_finance":(255,215,0),"crypto":(255,160,0),"real_estate":(100,220,100),"side_hustle":(50,150,255)}
    c = colors.get(niche,(80,0,100)); a = accents.get(niche,(255,215,0))
    words = ai_result["script"].upper().split(); lines = []; chunk = []
    for w in words[:64]:
        chunk.append(w)
        if len(" ".join(chunk)) > 13: lines.append(" ".join(chunk)); chunk=[]
    if chunk: lines.append(" ".join(chunk))
    return {"title": ctitle or ai_result["title"], "script": ai_result["script"],
            "color": c, "accent": a, "lines": lines[:8] or ["WATCH NOW","SUBSCRIBE"],
            "niche": niche, "topic": topic, "tags": ai_result.get("tags", [])}

def script_from_prompt(prompt, title, niche):
    colors  = {"personal_finance":(160,15,15),"crypto":(160,70,0),"real_estate":(15,55,15),"side_hustle":(0,55,110)}
    accents = {"personal_finance":(255,215,0),"crypto":(255,160,0),"real_estate":(100,220,100),"side_hustle":(50,150,255)}
    c = colors.get(niche,(80,0,100)); a = accents.get(niche,(255,215,0))
    script_text = prompt
    # If OpenAI key available, generate a polished script from the prompt
    if OPENAI_KEY:
        try:
            import openai as _oai
            client = _oai.OpenAI(api_key=OPENAI_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content":
                    f"Write a 45-second YouTube Shorts script about '{prompt}' for a finance channel. "
                    "Shocking, urgent, valuable. Hook first. Specific numbers. CTA at end. Spoken words only."}],
                max_tokens=320, temperature=0.9,
            )
            script_text = resp.choices[0].message.content.strip()
            print(f"   [AI] Custom prompt enhanced by GPT-4o-mini")
        except Exception as e:
            print(f"   [AI] Enhancement failed ({e}), using raw prompt")
    out_title = title or prompt[:70]
    words = script_text.upper().split(); lines = []; chunk = []
    for w in words[:64]:
        chunk.append(w)
        if len(" ".join(chunk)) > 13: lines.append(" ".join(chunk)); chunk=[]
    if chunk: lines.append(" ".join(chunk))
    return {"title": out_title, "script": script_text, "color": c, "accent": a,
            "lines": lines[:10] or ["WATCH THIS","RIGHT NOW"], "niche": niche, "topic": prompt}

def process(job):
    db=get_db(); jid=job["id"]; uid=job["user_id"]; cid=job["channel_id"]
    vtype=job["video_type"]; niche=job["niche"]
    cprompt=job["custom_prompt"] if job["custom_prompt"] else None
    ctitle=job["custom_title"] if job["custom_title"] else None
    print(f"\n{'='*52}\n⚡ Job {jid} | {vtype.upper()} | {niche}\n{'='*52}")
    pg_execute(db, "UPDATE queue SET status='processing' WHERE id=?",(jid,)); db.commit()
    sd={}

    def prog(msg):
        try:
            d2=get_db(); pg_execute(d2, "UPDATE queue SET progress=? WHERE id=?",(msg,jid)); d2.commit(); d2.close()
        except: pass
        print(f"   {msg}")

    def done_fail(reason):
        short=str(reason)[:200]; print(f"\nFAILED: {short}")
        pg_execute(db, "UPDATE queue SET status='failed',progress=? WHERE id=?",(f"Failed: {short}",jid))
        pg_execute(db, "INSERT INTO videos (user_id,channel_id,title,type,status,error_msg) VALUES (?,?,?,?,'failed',?)",(uid,cid,sd.get("title","Unknown"),vtype,short))
        db.commit(); db.close()

    try:
        # ── Custom upload: skip generation, go straight to YouTube ─────────
        try:
            video_file_path = job["video_file_path"]
        except (KeyError, IndexError, TypeError):
            video_file_path = None

        if vtype == "custom_upload" and video_file_path and os.path.exists(str(video_file_path)):
            prog("Refreshing YouTube token...")
            ch=_fetchone(db, "SELECT * FROM channels WHERE id=?",(cid,))
            if not ch: raise Exception("Channel not found")
            token=refresh_yt_token(ch["refresh_token"])
            title=ctitle or "My Video"
            prog("Uploading your video to YouTube...")
            mp4=str(video_file_path)
            desc=f"{title}\n\n#finance #investing #money #youtube"
            tags=["finance","money","investing","youtube"]
            vid_id=upload_youtube(token,mp4,title,desc,tags)
            if not vid_id: raise Exception("YouTube returned no video ID")
            yt_url=f"https://youtube.com/watch?v={vid_id}"
            print(f"   LIVE: {yt_url}")
            if _HAS_PG and DATABASE_URL:
                cur=pg_execute(db,"INSERT INTO videos (user_id,channel_id,title,type,status,youtube_id,youtube_url,script) VALUES (?,?,?,?,'uploaded',?,?,?) RETURNING id",(uid,cid,title,"custom_upload",vid_id,yt_url,"User uploaded video"))
                vid_row_id=cur.fetchone()[0]
            else:
                cur=pg_execute(db,"INSERT INTO videos (user_id,channel_id,title,type,status,youtube_id,youtube_url,script) VALUES (?,?,?,?,'uploaded',?,?,?)",(uid,cid,title,"custom_upload",vid_id,yt_url,"User uploaded video"))
                vid_row_id=cur.lastrowid
            pg_execute(db,"UPDATE channels SET videos_uploaded=videos_uploaded+1 WHERE id=?",(cid,))
            pg_execute(db,"UPDATE queue SET status='done',progress='Uploaded to YouTube!' WHERE id=?",(jid,))
            db.commit(); db.close()
            print(f"Job {jid} COMPLETE (custom upload)!")
            return

        prog("Refreshing YouTube token...")
        ch=_fetchone(db, "SELECT * FROM channels WHERE id=?",(cid,))
        if not ch: raise Exception("Channel not found")
        token=refresh_yt_token(ch["refresh_token"])

        if cprompt:
            prog("Using custom prompt...")
            sd = script_from_prompt(cprompt, ctitle, niche)
        else:
            topic = get_next_topic(niche, cid)
            prog(f"AI topic: {topic}")
            ai_result = ai_generate_script(topic, niche)
            if ai_result:
                sd = _build_sd_from_ai(ai_result, topic, niche, ctitle)
            else:
                # Built-in library fallback (no OpenAI key)
                all_scripts = SCRIPTS.get(niche, SCRIPTS["personal_finance"]) + SCRIPTS.get(niche+"_extra", [])
                sd = dict(random.choice(all_scripts)); sd["niche"] = niche; sd["topic"] = topic
        print(f"   Title: {sd['title']}")

        wd=OUT/f"job_{jid}"; wd.mkdir(exist_ok=True)
        prog("Generating voice narration...")
        wav=str(wd/"voice.wav")
        user_row=_fetchone(db, "SELECT custom_voice_id FROM users WHERE id=?",(uid,))
        voice_id=user_row["custom_voice_id"] if user_row and user_row["custom_voice_id"] else None
        if not make_voice(sd["script"],wav,voice_id=voice_id): raise Exception("Voice failed — set ELEVENLABS_API_KEY or ensure gTTS is installed (pip install gtts)")
        dur=get_duration(wav); print(f"   Duration: {dur:.1f}s")

        prog("Generating background music...")
        music=str(wd/"music.wav"); make_music(music,dur=int(dur)+2)

        prog("Mixing audio...")
        mixed=str(wd/"mixed.wav")
        subprocess.run([FFMPEG,"-y","-i",wav,"-i",music,"-filter_complex","[0:a]volume=2.0[v];[1:a]volume=0.08[m];[v][m]amix=inputs=2:duration=first[out]","-map","[out]","-ar","44100",mixed],capture_output=True)
        if not os.path.exists(mixed): mixed=wav

        prog("Fetching AI background...")
        bg_path = get_ai_background(sd.get("topic", niche.replace("_", " ")), vtype)

        prog("Generating video frames...")
        fdir=str(wd/"frames"); fps=make_frames(sd,dur,fdir,vtype,bg_path=bg_path)

        prog("Rendering final video...")
        mp4=str(wd/"video.mp4")
        if not render_video(fdir,mixed,mp4,fps): raise Exception("Render failed — check ffmpeg at ~/Downloads/ffmpeg")
        print(f"   Rendered: {os.path.getsize(mp4)/1024/1024:.1f}MB")

        thumb=str(wd/"thumb.jpg"); make_thumb(sd,thumb,vtype)

        prog("Uploading to YouTube...")
        desc=f"{sd['title']}\n\n{sd['script']}\n\n🔔 Subscribe!\n\n#personalfinance #money #finance #investing"
        base_tags=["personalfinance","money","finance","moneytips","wealth","investing","shorts"]
        tags=list(dict.fromkeys(base_tags + sd.get("tags",[])))[:15]
        vid_id=upload_youtube(token,mp4,sd["title"],desc,tags)
        if not vid_id: raise Exception("YouTube returned no video ID")
        upload_thumb(token,vid_id,thumb)
        yt_url=f"https://youtube.com/{'shorts/' if vtype=='short' else 'watch?v='}{vid_id}"
        print(f"   LIVE: {yt_url}")

        if _HAS_PG and DATABASE_URL:
            cur = pg_execute(db, "INSERT INTO videos (user_id,channel_id,title,type,status,youtube_id,youtube_url,script) VALUES (?,?,?,?,'uploaded',?,?,?) RETURNING id",(uid,cid,sd["title"],vtype,vid_id,yt_url,sd["script"]))
            vid_row_id = cur.fetchone()[0]
        else:
            cur = pg_execute(db, "INSERT INTO videos (user_id,channel_id,title,type,status,youtube_id,youtube_url,script) VALUES (?,?,?,?,'uploaded',?,?,?)",(uid,cid,sd["title"],vtype,vid_id,yt_url,sd["script"]))
            vid_row_id = cur.lastrowid
        pg_execute(db, "UPDATE channels SET videos_uploaded=videos_uploaded+1 WHERE id=?",(cid,))
        pg_execute(db, "UPDATE queue SET status='done',progress='Uploaded to YouTube!' WHERE id=?",(jid,))
        db.commit(); db.close()
        print(f"Job {jid} COMPLETE!")
        prog("Cross-posting to social media...")
        cross_post_social(cid,vid_row_id,yt_url,sd["title"],niche,thumb)
        # Auto-post to FinanceFlow's own Twitter if configured
        try:
            db2=get_db()
            row=_fetchone(db2, "SELECT value FROM system_settings WHERE key='auto_post_on_upload'")
            db2.close()
            if row and str(row["value"])=="1":
                sys_creds={"api_key":os.environ.get("SYSTEM_TWITTER_API_KEY",""),
                           "api_secret":os.environ.get("SYSTEM_TWITTER_API_SECRET",""),
                           "access_token":os.environ.get("SYSTEM_TWITTER_ACCESS_TOKEN",""),
                           "access_secret":os.environ.get("SYSTEM_TWITTER_ACCESS_SECRET","")}
                if all(sys_creds.values()):
                    tweet_text=f"🚀 Another creator just automated their YouTube channel with FinanceFlow!\n\n{yt_url}\n\n#YouTubeAutomation #AIContent #FinanceFlow #PassiveIncome"[:280]
                    post_twitter(sys_creds,yt_url,tweet_text,niche)
                    print("   📣 System Twitter post sent")
        except Exception as e:
            print(f"   System tweet failed: {e}")
    except Exception as e:
        done_fail(e)

def check_autopilot():
    """Queue one video per channel that has autopilot=1, respecting its upload_schedule."""
    import datetime
    SCHEDULE_HOURS = {"daily": 24, "twice_daily": 12, "weekly": 168}
    db = get_db()
    try:
        channels = _fetchall(db, "SELECT * FROM channels WHERE autopilot=1 AND active=1")
        queued = 0
        for ch in channels:
            schedule = (ch["schedule"] or "daily").lower()
            if schedule == "manual":
                continue  # Never auto-queue manual channels
            hours_needed = SCHEDULE_HOURS.get(schedule, 24)
            last_job = _fetchone(db,
                "SELECT created_at FROM queue WHERE channel_id=? "
                "ORDER BY created_at DESC LIMIT 1", (ch["id"],))
            if last_job:
                try:
                    last_dt = datetime.datetime.fromisoformat(last_job["created_at"])
                    age_h = (datetime.datetime.utcnow() - last_dt).total_seconds() / 3600
                    if age_h < hours_needed:
                        continue
                except Exception:
                    pass
            # Auto-queue a video for this channel
            niche = ch["niche"] or "personal_finance"
            pg_execute(db,
                "INSERT INTO queue (user_id, channel_id, video_type, niche, mode) VALUES (?,?,?,?,'auto')",
                (ch["user_id"], ch["id"], ch["video_type"] or "short", niche))
            db.commit()
            queued += 1
            print(f"   [AUTOPILOT] Queued video for channel {ch['channel_name']} (id={ch['id']})")
        return queued
    except Exception as e:
        print(f"   [AUTOPILOT] Error: {e}")
        return 0
    finally:
        db.close()

def check_system_channel():
    """Queue a daily promo video for FinanceFlow's own system YouTube channel."""
    import datetime
    db = get_db()
    try:
        row = _fetchone(db, "SELECT value FROM system_settings WHERE key='system_channel_id'")
        if not row or not row["value"]:
            return 0
        cid = int(row["value"])
        ch = _fetchone(db, "SELECT * FROM channels WHERE id=? AND active=1", (cid,))
        if not ch:
            print(f"   [SYSTEM_CH] Channel id={cid} not found or inactive")
            return 0
        # Check if a promo video was already queued in the last 20 hours
        last_job = _fetchone(db,
            "SELECT created_at FROM queue WHERE channel_id=? ORDER BY created_at DESC LIMIT 1",
            (cid,))
        if last_job:
            try:
                last_dt = datetime.datetime.fromisoformat(str(last_job["created_at"]))
                age_h = (datetime.datetime.utcnow() - last_dt).total_seconds() / 3600
                if age_h < 20:
                    return 0
            except Exception:
                pass
        uid = ch["user_id"]
        pg_execute(db,
            "INSERT INTO queue (user_id, channel_id, video_type, niche, mode) VALUES (?,?,?,?,'auto')",
            (uid, cid, "short", "financeflow_promo"))
        db.commit()
        print(f"   [SYSTEM_CH] Queued promo video for system channel id={cid}")
        return 1
    except Exception as e:
        print(f"   [SYSTEM_CH] Error: {e}")
        return 0
    finally:
        db.close()

if __name__=="__main__":
    print("\n==============================================")
    print("  FinanceFlow Worker — Launch Version")
    print("  Polls queue every 10s | Ctrl+C to stop")
    print("==============================================")
    print(f"DB: {DB}")
    print(f"PG: {'YES — ' + DATABASE_URL[:40] + '...' if _HAS_PG and DATABASE_URL else 'NO — using SQLite'}")
    if not FFMPEG:
        print("[WARN] ffmpeg not found in PATH — moviepy fallback will be used for rendering")
    else:
        print(f"ffmpeg: {FFMPEG}")
    try: from PIL import Image; print("Pillow: ready")
    except: print("ERROR: pip3 install Pillow --break-system-packages"); sys.exit(1)
    print(f"Output dir: {OUT}\n")

    # ── Ensure all DB tables exist (important on fresh PostgreSQL) ────────
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app import init_db
        init_db()
        print("[STARTUP] init_db() complete")
    except Exception as e:
        print(f"[STARTUP] init_db() failed: {e}")

    # ── Reset any jobs stuck in 'processing' from a previous crash ───────
    try:
        db = get_db()
        stuck = _fetchone(db, "SELECT COUNT(*) FROM queue WHERE status='processing'")[0]
        if stuck:
            print(f"[STARTUP] Found {stuck} job(s) stuck in 'processing' — resetting to 'pending'")
            _db_exec(db, "UPDATE queue SET status='pending', progress='Requeued after worker restart' WHERE status='processing'")
            db.commit()
        else:
            print("[STARTUP] No stuck jobs found")
        total_pending = _fetchone(db, "SELECT COUNT(*) FROM queue WHERE status='pending'")[0]
        total_all     = _fetchone(db, "SELECT COUNT(*) FROM queue")[0]
        print(f"[STARTUP] Queue: {total_pending} pending, {total_all} total rows")
        db.close()
    except Exception as e:
        print(f"[STARTUP] DB check failed: {e}")

    idle_count = 0
    while True:
        try:
            with open(HBEAT, "w") as f:
                f.write(str(time.time()))
            db = get_db()

            # ── Debug: show live queue snapshot every poll ────────────────
            n_pending    = _fetchone(db, "SELECT COUNT(*) FROM queue WHERE status='pending'")[0]
            n_processing = _fetchone(db, "SELECT COUNT(*) FROM queue WHERE status='processing'")[0]
            n_done       = _fetchone(db, "SELECT COUNT(*) FROM queue WHERE status='done'")[0]
            n_failed     = _fetchone(db, "SELECT COUNT(*) FROM queue WHERE status='failed'")[0]
            ts = time.strftime('%H:%M:%S')

            job = _fetchone(db, "SELECT * FROM queue WHERE status='pending' ORDER BY created_at ASC LIMIT 1")
            db.close()

            if job:
                idle_count = 0
                print(f"[{ts}] Poll: pending={n_pending} processing={n_processing} done={n_done} failed={n_failed}")
                print(f"[{ts}] ▶ Picked job id={job['id']} | niche={job['niche']} | type={job['video_type']} | channel_id={job['channel_id']} | user_id={job['user_id']}")
                process(job)
            else:
                idle_count += 1
                print(f"[{ts}] Poll: pending={n_pending} processing={n_processing} done={n_done} failed={n_failed} | idle #{idle_count}")
                # Check autopilot + system channel every 6 idle cycles (~60s)
                if idle_count % 6 == 0:
                    n = check_autopilot()
                    if n:
                        print(f"[{ts}] [AUTOPILOT] {n} job(s) queued")
                    s = check_system_channel()
                    if s:
                        print(f"[{ts}] [SYSTEM_CH] Promo video queued")

        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            import traceback
            print(f"\n[{time.strftime('%H:%M:%S')}] Worker error: {e}")
            traceback.print_exc()
        time.sleep(10)
