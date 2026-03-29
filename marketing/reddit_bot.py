"""
FinanceFlow Reddit Marketing Bot
Monitors YouTube/creator/finance subreddits and posts helpful content.
Run manually or via GitHub Actions cron.

Setup:
  pip install praw
  Set env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD
"""

import os
import praw
import time
import json
import random
from datetime import datetime

APP_URL = "https://financeflow-saas.vercel.app"
APP_NAME = "FinanceFlow"

MONITOR_SUBS = [
    "NewTubers",
    "youtubers",
    "passive_income",
    "personalfinance",
    "financialindependence",
    "sidehustle",
    "Entrepreneur",
    "ContentCreators",
]

PROMO_SUBS = [
    "SideProject",
    "entrepreneur",
    "startups",
    "indiehackers",
    "passive_income",
]

TRIGGER_KEYWORDS = [
    "youtube automation",
    "automate youtube",
    "youtube channel passive",
    "passive income youtube",
    "faceless youtube",
    "how to grow youtube",
    "youtube without showing",
    "youtube channel ideas",
    "monetize youtube",
    "make money youtube",
    "youtube views",
    "youtube shorts automation",
    "finance youtube channel",
    "content creator tools",
]

HELPFUL_REPLIES = [
    """Good question on YouTube automation. The channels that grow fastest in the finance/investing niche right now are doing a few things differently:

1. Posting Shorts consistently (daily if possible — YouTube's algorithm rewards this heavily)
2. Using a single tight niche ("index fund investing" vs "personal finance" — narrower wins)
3. Scripting based on trending search queries, not just topics they know

I've been running an automated finance channel with a tool called {app} ({url}) — it generates scripts, creates the video, and uploads directly to YouTube. Cut the production time from 3 hours to about 10 minutes per video. Still in early days but the consistency has definitely helped.

Happy to answer questions about the setup.""",

    """The hardest part of YouTube is consistency — most channels die because the creator burns out after 2 months.

Tools that help:
- Script templates for your niche (stop reinventing every video)
- Short-form video generators (Shorts are 80% of new channel growth right now)
- Scheduling + batch recording sessions

I use {app} ({url}) for the whole pipeline — script → voiceover → video → upload. Fully automated for finance content. It's not perfect but it handles the 90% of videos that are "solid and consistent" which is what algorithms reward.

What niche are you targeting?""",

    """Finance YouTube is honestly one of the better niches right now because:
- High CPM ($8-25 vs $1-3 for entertainment)
- Evergreen content ("How to build an emergency fund" gets views for years)
- Low face-on-camera barrier (charts + voiceover works)

For automation specifically, I built a system using {app} ({url}) — picks trending finance topics, generates a script, creates a narrated video with stock footage-style visuals, and uploads to YouTube. Running ~7 videos/week on autopilot now.

The key is to pick ONE sub-niche and dominate it before expanding.""",
]

WEEKLY_POST_TITLE = [
    "I built a YouTube automation tool for finance channels — here's how it works [Show & Tell]",
    "6 months of automated YouTube: what actually works for passive income channels",
    "[Side Project] FinanceFlow — AI that writes, records, and uploads YouTube finance videos automatically",
]

WEEKLY_POST_BODY = """**The problem:** Finance YouTube is lucrative ($8-25 CPM) but most creators burn out because consistent content is brutal to produce.

**What I built:** FinanceFlow — an AI system that takes a topic, writes a script, generates a narrated video with professional visuals, and uploads directly to YouTube. Daily, automatically.

**How it works technically:**
- Flask backend + SQLite job queue
- OpenAI for script generation (finance-specific prompts)
- ElevenLabs for voice synthesis
- FFmpeg for video rendering at 24fps with animated charts
- YouTube Data API for automatic upload + thumbnail

**Results so far:**
- 3 channels running on autopilot
- ~7 videos/week per channel
- No manual work after initial setup

**Why this beats just using ChatGPT + CapCut manually:**
The whole pipeline is one click. Topic → live video in ~8 minutes. No editing, no recording, no scheduling.

**Try it:** {url}

---
*Built for the finance niche specifically — scripts are optimized for high CPM keywords, thumbnails are A/B tested, and it tracks which video types get the best retention.*"""


def get_reddit_client():
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=f"{APP_NAME}/1.0 by u/{os.environ['REDDIT_USERNAME']}",
    )


def already_replied(post_id, log_file="replied_ff.json"):
    try:
        with open(log_file) as f:
            replied = json.load(f)
        return post_id in replied
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def log_reply(post_id, log_file="replied_ff.json"):
    try:
        with open(log_file) as f:
            replied = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        replied = {}
    replied[post_id] = datetime.utcnow().isoformat()
    with open(log_file, "w") as f:
        json.dump(replied, f, indent=2)


def is_relevant(post):
    text = (post.title + " " + (post.selftext or "")).lower()
    return any(kw in text for kw in TRIGGER_KEYWORDS)


def monitor_and_reply(reddit, dry_run=False):
    replied_count = 0
    for sub_name in MONITOR_SUBS:
        sub = reddit.subreddit(sub_name)
        print(f"Scanning r/{sub_name}...")
        try:
            for post in sub.new(limit=25):
                if already_replied(post.id):
                    continue
                if not is_relevant(post):
                    continue
                age_hours = (time.time() - post.created_utc) / 3600
                if age_hours > 6:
                    continue
                reply = random.choice(HELPFUL_REPLIES).format(app=APP_NAME, url=APP_URL)
                print(f"\n[r/{sub_name}] Relevant: {post.title[:80]}")
                if not dry_run:
                    post.reply(reply)
                    log_reply(post.id)
                    replied_count += 1
                    time.sleep(30)
                else:
                    print(f"[DRY RUN] Would reply:\n{reply[:200]}...")
                    log_reply(post.id)
        except Exception as e:
            print(f"  Error scanning r/{sub_name}: {e}")
    print(f"\nReplied to {replied_count} posts.")
    return replied_count


def post_weekly_promo(reddit, dry_run=False):
    log_file = "promo_log_ff.json"
    try:
        with open(log_file) as f:
            promo_log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        promo_log = {}

    week = datetime.utcnow().strftime("%Y-W%W")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    posted = 0

    for sub_name in PROMO_SUBS:
        key = f"{sub_name}:{week}"
        if key in promo_log:
            print(f"Already posted to r/{sub_name} this week, skipping.")
            continue
        title = random.choice(WEEKLY_POST_TITLE)
        body = WEEKLY_POST_BODY.format(url=APP_URL)
        print(f"\nPosting to r/{sub_name}: {title[:60]}...")
        if not dry_run:
            try:
                sub = reddit.subreddit(sub_name)
                sub.submit(title, selftext=body)
                promo_log[key] = today
                with open(log_file, "w") as f:
                    json.dump(promo_log, f, indent=2)
                posted += 1
                time.sleep(60)
            except Exception as e:
                print(f"  Error posting to r/{sub_name}: {e}")
        else:
            print(f"[DRY RUN] Would post to r/{sub_name}")
            promo_log[key] = today
            with open(log_file, "w") as f:
                json.dump(promo_log, f, indent=2)

    print(f"\nPosted to {posted} subreddits.")
    return posted


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["monitor", "promo", "both"], default="monitor")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reddit = get_reddit_client()
    print(f"Logged in as: {reddit.user.me()}")

    if args.mode in ("monitor", "both"):
        monitor_and_reply(reddit, dry_run=args.dry_run)
    if args.mode in ("promo", "both"):
        post_weekly_promo(reddit, dry_run=args.dry_run)
