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
ELEVENLABS_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
OPENAI_KEY      = os.environ.get("OPENAI_API_KEY", "")

def find_ffmpeg():
    # System PATH first (works on Railway/Linux after nixpacks installs ffmpeg)
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    # Mac/local fallbacks
    for p in [os.path.expanduser("~/Downloads/ffmpeg"),"/opt/homebrew/bin/ffmpeg","/usr/local/bin/ffmpeg","/usr/bin/ffmpeg"]:
        if os.path.exists(p):
            try: os.chmod(p, 0o755)
            except: pass
            return p
    return None
FFMPEG = find_ffmpeg()

def fnt(size):
    for p in ["/System/Library/Fonts/Helvetica.ttc","/System/Library/Fonts/Supplemental/Impact.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        try: return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()

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
}

def get_db():
    if _HAS_PG and DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
        conn.autocommit = False
        return conn
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def _db_exec(db, sql, params=()):
    """Execute a query that works on both SQLite and PostgreSQL."""
    if _HAS_PG and DATABASE_URL:
        sql = sql.replace("?", "%s")
    cur = db.cursor() if _HAS_PG and DATABASE_URL else db
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur

def _fetchone(db, sql, params=()):
    cur = _db_exec(db, sql, params)
    return cur.fetchone()

def _fetchall(db, sql, params=()):
    cur = _db_exec(db, sql, params)
    return cur.fetchall()

def refresh_yt_token(rt):
    data=urllib.parse.urlencode({"refresh_token":rt,"client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,"grant_type":"refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token",data=data,headers={"Content-Type":"application/x-www-form-urlencoded"})) as r:
        return json.loads(r.read())["access_token"]

def make_voice(text, out_wav, voice_id=None, rate=165):
    # Try ElevenLabs first if key is available
    if ELEVENLABS_KEY:
        try:
            vid = voice_id or "pNInz6obpgDQGcFmaJgB"  # Adam voice
            payload = json.dumps({
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
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
            print(f"   ElevenLabs failed ({e}), falling back to Mac say...")
    # Fallback: gTTS (works on Linux/Railway)
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

def make_music(out,dur=60):
    sr=44100
    chords=[[261.63,329.63,392],[392,493.88,587.33],[220,261.63,329.63],[349.23,440,523.25]]
    frames=[]
    for i in range(sr*int(dur+2)):
        t=i/sr; ci=int(t*0.5)%len(chords); pos=(t*0.5)%1
        env=min(pos/0.1,1,(1-pos)/0.1); master=min(t/0.5,1,(dur-t)/0.5)
        s=sum(0.09*math.sin(2*math.pi*f*t+j*0.1) for j,f in enumerate(chords[ci]))
        bass=0.06*math.sin(2*math.pi*chords[ci][0]*0.5*t)
        beat=(t*120/60)%1
        kick=0.12*(1-beat/0.04)*math.sin(2*math.pi*55*t) if beat<0.04 else 0
        hh=0.03*random.gauss(0,1) if beat<0.02 or 0.5<=beat<0.52 else 0
        val=int((s*env+bass+kick+hh)*master*20000)
        frames.append(struct.pack('<h',max(-32767,min(32767,val))))
    with wave.open(out,'w') as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(b''.join(frames))

def make_frames(sd,dur,fdir,vtype):
    os.makedirs(fdir,exist_ok=True)
    W,H=(1080,1920) if vtype=="short" else (1920,1080)
    FPS=24; c,a=sd["color"],sd["accent"]; lines=sd["lines"]
    nf=int(dur*FPS); cd=dur/max(len(lines),1)
    for f in range(nf):
        t=f/FPS; li=min(int(t/cd),len(lines)-1)
        img=Image.new("RGB",(W,H)); draw=ImageDraw.Draw(img)
        wp=math.sin(t*0.5)*0.15
        for y in range(H):
            draw.line([(0,y),(W,y)],fill=(max(0,min(255,c[0]+int((30+wp*20)*y/H))),max(0,min(255,c[1]+int((20+wp*10)*y/H))),max(0,min(255,c[2]+int((35+wp*30)*y/H)))))
        draw.rectangle([0,0,W,8],fill=a); draw.rectangle([0,H-8,W,H],fill=a)
        prog=int((t/dur)*(W-80)); draw.rectangle([40,H-6,40+max(prog,4),H-2],fill=a)
        draw.text((W//2,44),"FINANCE CHANNEL",fill=a,font=fnt(32),anchor="mm")
        draw.text((W//2,H-24),"Made with FinanceFlow.app",fill=(80,80,80),font=fnt(14),anchor="mm")
        line=lines[li] if li<len(lines) else ""
        yoff=int((1-min(((t-li*cd)/cd)*5,1))*40)
        tsz=int((82 if vtype=="short" else 68)*(1+0.03*math.sin(t*6)))
        draw.text((W//2,H//2+yoff),line,fill=a,font=fnt(tsz),anchor="mm")
        fade=int(FPS*0.2)
        if f<fade:
            dk=Image.new("RGB",(W,H),(0,0,0)); img=Image.blend(dk,img,f/fade)
        elif f>nf-fade:
            dk=Image.new("RGB",(W,H),(0,0,0)); img=Image.blend(dk,img,max(0,(nf-f)/fade))
        img.save(f"{fdir}/f{f:06d}.jpg",quality=78)
    return FPS

def make_thumb(sd,out,vtype):
    W,H=(1080,1920) if vtype=="short" else (1280,720)
    img=Image.new("RGB",(W,H)); draw=ImageDraw.Draw(img); c,a=sd["color"],sd["accent"]
    for y in range(H):
        draw.line([(0,y),(W,y)],fill=(max(0,min(255,c[0]+30*y//H)),max(0,min(255,c[1]+20*y//H)),max(0,min(255,c[2]+35*y//H))))
    draw.rectangle([0,0,W,10],fill=a); draw.rectangle([0,H-10,W,H],fill=a)
    title_text=sd["title"][:40]
    draw.text((W//2,H//2-60),title_text,fill=a,font=fnt(64 if vtype=="short" else 80),anchor="mm")
    draw.text((W//2,H-50),"Subscribe for more",fill=(180,180,180),font=fnt(28),anchor="mm")
    img.save(out,quality=95)

def render_video(fdir,audio,out,fps):
    if FFMPEG:
        r=subprocess.run([FFMPEG,"-y","-framerate",str(fps),"-i",f"{fdir}/f%06d.jpg","-i",audio,"-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",out],capture_output=True)
        if os.path.exists(out): return True
    # moviepy fallback (no system ffmpeg needed)
    try:
        from moviepy.editor import ImageSequenceClip, AudioFileClip
        frames = sorted([f"{fdir}/{fn}" for fn in os.listdir(fdir) if fn.endswith(".jpg")])
        clip = ImageSequenceClip(frames, fps=fps)
        aclip = AudioFileClip(audio)
        clip = clip.set_audio(aclip)
        clip.write_videofile(out, codec="libx264", audio_codec="aac", logger=None)
        return os.path.exists(out)
    except Exception as e:
        print(f"   moviepy fallback failed: {e}")
        return False

def upload_youtube(token,mp4,title,desc,tags):
    fs=os.path.getsize(mp4)
    meta=json.dumps({"snippet":{"title":title[:100],"description":desc[:4990],"tags":[t[:30] for t in tags[:15]],"categoryId":"22","defaultLanguage":"en"},"status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}).encode()
    try:
        init=urllib.request.Request("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",data=meta,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json; charset=UTF-8","X-Upload-Content-Type":"video/mp4","X-Upload-Content-Length":str(fs)})
        with urllib.request.urlopen(init) as r: up_url=r.headers["Location"]
    except urllib.error.HTTPError as e:
        raise Exception(f"Upload init failed: {e.read().decode()[:150]}")
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
    accounts=db.execute("SELECT * FROM social_accounts WHERE channel_id=? AND active=1",(channel_id,)).fetchall()
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
        db.execute("INSERT INTO social_posts (video_id,channel_id,platform,post_url,status,error_msg) VALUES (?,?,?,?,?,?)",(video_id,channel_id,platform,post_url,status,err))
        db.commit(); db.close()

def script_from_prompt(prompt,title,niche):
    colors={"personal_finance":(160,15,15),"crypto":(160,70,0),"real_estate":(15,55,15),"side_hustle":(0,55,110)}
    accents={"personal_finance":(255,215,0),"crypto":(255,160,0),"real_estate":(100,220,100),"side_hustle":(50,150,255)}
    c=colors.get(niche,(80,0,100)); a=accents.get(niche,(255,215,0))
    out_title=title or f"Finance Tip — {niche.replace('_',' ').title()}"
    words=prompt.upper().split(); lines=[]; chunk=[]
    for w in words[:60]:
        chunk.append(w)
        if len(" ".join(chunk))>13: lines.append(" ".join(chunk)); chunk=[]
    if chunk: lines.append(" ".join(chunk))
    return {"title":out_title,"script":prompt,"color":c,"accent":a,"lines":lines[:10] or ["WATCH THIS","RIGHT NOW"]}

def process(job):
    db=get_db(); jid=job["id"]; uid=job["user_id"]; cid=job["channel_id"]
    vtype=job["video_type"]; niche=job["niche"]
    cprompt=job["custom_prompt"] if job["custom_prompt"] else None
    ctitle=job["custom_title"] if job["custom_title"] else None
    print(f"\n{'='*52}\n⚡ Job {jid} | {vtype.upper()} | {niche}\n{'='*52}")
    db.execute("UPDATE queue SET status='processing' WHERE id=?",(jid,)); db.commit()
    sd={}

    def prog(msg):
        try:
            d2=get_db(); d2.execute("UPDATE queue SET progress=? WHERE id=?",(msg,jid)); d2.commit(); d2.close()
        except: pass
        print(f"   {msg}")

    def done_fail(reason):
        short=str(reason)[:200]; print(f"\nFAILED: {short}")
        db.execute("UPDATE queue SET status='failed',progress=? WHERE id=?",(f"Failed: {short}",jid))
        db.execute("INSERT INTO videos (user_id,channel_id,title,type,status,error_msg) VALUES (?,?,?,?,'failed',?)",(uid,cid,sd.get("title","Unknown"),vtype,short))
        db.commit(); db.close()

    try:
        prog("Refreshing YouTube token...")
        ch=db.execute("SELECT * FROM channels WHERE id=?",(cid,)).fetchone()
        if not ch: raise Exception("Channel not found")
        token=refresh_yt_token(ch["refresh_token"])

        if cprompt:
            prog("Using custom prompt..."); sd=script_from_prompt(cprompt,ctitle,niche)
        else:
            sd=random.choice(SCRIPTS.get(niche,SCRIPTS["personal_finance"]))
        print(f"   Title: {sd['title']}")

        wd=OUT/f"job_{jid}"; wd.mkdir(exist_ok=True)
        prog("Generating voice narration...")
        wav=str(wd/"voice.wav")
        user_row=db.execute("SELECT custom_voice_id FROM users WHERE id=?",(uid,)).fetchone()
        voice_id=user_row["custom_voice_id"] if user_row and user_row["custom_voice_id"] else None
        if not make_voice(sd["script"],wav,voice_id=voice_id): raise Exception("Voice failed — set ELEVENLABS_API_KEY or ensure gTTS is installed (pip install gtts)")
        dur=get_duration(wav); print(f"   Duration: {dur:.1f}s")

        prog("Generating background music...")
        music=str(wd/"music.wav"); make_music(music,dur=int(dur)+2)

        prog("Mixing audio...")
        mixed=str(wd/"mixed.wav")
        subprocess.run([FFMPEG,"-y","-i",wav,"-i",music,"-filter_complex","[0:a]volume=2.0[v];[1:a]volume=0.08[m];[v][m]amix=inputs=2:duration=first[out]","-map","[out]",mixed],capture_output=True)
        if not os.path.exists(mixed): mixed=wav

        prog("Generating video frames...")
        fdir=str(wd/"frames"); fps=make_frames(sd,dur,fdir,vtype)

        prog("Rendering final video...")
        mp4=str(wd/"video.mp4")
        if not render_video(fdir,mixed,mp4,fps): raise Exception("Render failed — check ffmpeg at ~/Downloads/ffmpeg")
        print(f"   Rendered: {os.path.getsize(mp4)/1024/1024:.1f}MB")

        thumb=str(wd/"thumb.jpg"); make_thumb(sd,thumb,vtype)

        prog("Uploading to YouTube...")
        desc=f"{sd['title']}\n\n{sd['script']}\n\n🔔 Subscribe!\n\n#personalfinance #money #finance #investing"
        tags=["personalfinance","money","finance","moneytips","wealth","investing","shorts"]
        vid_id=upload_youtube(token,mp4,sd["title"],desc,tags)
        if not vid_id: raise Exception("YouTube returned no video ID")
        upload_thumb(token,vid_id,thumb)
        yt_url=f"https://youtube.com/{'shorts/' if vtype=='short' else 'watch?v='}{vid_id}"
        print(f"   LIVE: {yt_url}")

        db.execute("INSERT INTO videos (user_id,channel_id,title,type,status,youtube_id,youtube_url,script) VALUES (?,?,?,?,'uploaded',?,?,?)",(uid,cid,sd["title"],vtype,vid_id,yt_url,sd["script"]))
        vid_row_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("UPDATE channels SET videos_uploaded=videos_uploaded+1 WHERE id=?",(cid,))
        db.execute("UPDATE queue SET status='done',progress='Uploaded to YouTube!' WHERE id=?",(jid,))
        db.commit(); db.close()
        print(f"Job {jid} COMPLETE!")
        prog("Cross-posting to social media...")
        cross_post_social(cid,vid_row_id,yt_url,sd["title"],niche,thumb)
        # Auto-post to FinanceFlow's own Twitter if configured
        try:
            db2=get_db()
            row=db2.execute("SELECT value FROM system_settings WHERE key='auto_post_on_upload'").fetchone()
            db2.close()
            if row and str(row["value"])=="1":
                sys_creds={"api_key":os.environ.get("SYSTEM_TWITTER_API_KEY",""),
                           "api_secret":os.environ.get("SYSTEM_TWITTER_API_SECRET",""),
                           "access_token":os.environ.get("SYSTEM_TWITTER_ACCESS_TOKEN",""),
                           "access_secret":os.environ.get("SYSTEM_TWITTER_ACCESS_SECRET","")}
                if all(sys_creds.values()):
                    tweet_text=f"🚀 New finance video just dropped: {sd['title']}\n\nMade with FinanceFlow.app — AI YouTube automation\n\n{yt_url}\n\n#personalfinance #finance #money"[:280]
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
        channels = db.execute(
            "SELECT * FROM channels WHERE autopilot=1 AND active=1"
        ).fetchall()
        queued = 0
        for ch in channels:
            schedule = (ch["schedule"] or "daily").lower()
            if schedule == "manual":
                continue  # Never auto-queue manual channels
            hours_needed = SCHEDULE_HOURS.get(schedule, 24)
            last_job = db.execute(
                "SELECT created_at FROM queue WHERE channel_id=? "
                "ORDER BY created_at DESC LIMIT 1", (ch["id"],)
            ).fetchone()
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
            db.execute(
                "INSERT INTO queue (user_id, channel_id, video_type, niche, mode) VALUES (?,?,?,?,'auto')",
                (ch["user_id"], ch["id"], ch["video_type"] or "short", niche)
            )
            db.commit()
            queued += 1
            print(f"   [AUTOPILOT] Queued video for channel {ch['channel_name']} (id={ch['id']})")
        return queued
    except Exception as e:
        print(f"   [AUTOPILOT] Error: {e}")
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
                # Check autopilot every 6 idle cycles (~60s)
                if idle_count % 6 == 0:
                    n = check_autopilot()
                    if n:
                        print(f"[{ts}] [AUTOPILOT] {n} job(s) queued")

        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            import traceback
            print(f"\n[{time.strftime('%H:%M:%S')}] Worker error: {e}")
            traceback.print_exc()
        time.sleep(10)
