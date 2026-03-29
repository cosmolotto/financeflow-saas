"""
FinanceFlow Twitter/X Marketing Bot
Posts daily tips and weekly promos about YouTube automation.

Setup:
  pip install tweepy
  Set env vars: TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""

import os
import random
import tweepy

APP_URL = "https://vercel-financeflow.vercel.app"

DAILY_TIPS = [
    "YouTube finance channels earn $8–25 CPM vs $1–3 for entertainment. The math is simple: same views, 10x the revenue. Niche down into personal finance, investing, or crypto. 📊",
    "Faceless YouTube is the best passive income model in 2025: no filming, no editing, post from anywhere. The top channels are 100% AI-generated scripts + voiceover + automated upload. 🤖",
    "The YouTube algorithm in 2025 rewards consistency over quality. 1 video/day at 70% quality beats 1 video/week at 100% quality. Automation is the only way to sustain it long-term.",
    "Finance YouTube channel math: 10k subs → ~$500–800/month from ads alone. Add digital products and that's $2k-5k. The channels that get there fastest post daily Shorts first. 📈",
    "The fastest way to 1,000 YouTube subscribers in 2025:\n→ Pick a tight niche (index investing, not 'finance')\n→ Post 1 Short per day\n→ Use searchable titles\n→ Stay consistent for 90 days\nMost quit at day 30.",
    "YouTube Shorts vs long-form for new channels:\n- Shorts: fast growth, low CPM (~$0.05)\n- Long-form: slow growth, high CPM ($8-25)\n\nStrategy: Shorts to build audience, long-form for revenue. Start with Shorts.",
    "3 evergreen YouTube finance formats that always perform:\n1. 'How I paid off $X in Y months'\n2. 'X investing mistakes beginners make'\n3. 'My $X/month passive income breakdown'\n\nSearch volume + relatable = winner.",
    "YouTube automation tools I actually use:\n→ Script: AI (OpenAI/Claude)\n→ Voice: ElevenLabs\n→ Video: Python + FFmpeg\n→ Upload: YouTube Data API\n→ Schedule: Cron job\n\nOr use @FinanceFlowAI for the whole pipeline.",
    "Why finance YouTube > other niches:\n✅ High CPM ($8-25)\n✅ Evergreen content\n✅ No face required\n✅ Affiliate opportunities (brokers, credit cards)\n✅ Can 100% automate\n\nThe barrier is consistency. Solve that and you win.",
    "The 90-day YouTube growth formula:\n- Days 1-30: 1 Short/day, test topics\n- Days 31-60: Double down on what worked, add long-form\n- Days 61-90: Systemize everything, enable autopilot\n\nMost channels die at day 30.",
]

PROMO_TWEETS = [
    f"I built a YouTube automation system for finance channels.\n\nWrite script → generate video → upload to YouTube. Fully automated.\n\nRunning 3 channels on autopilot, 7 videos/week each.\n\n→ {APP_URL}",
    f"FinanceFlow: AI that turns a topic into a live YouTube video in 8 minutes.\n\n• Writes the script\n• Generates narrated video with animated charts\n• Uploads to YouTube automatically\n\nBuilt for finance/investing channels.\n\n{APP_URL}",
    f"What if your YouTube channel ran itself?\n\nFinanceFlow does:\n✅ Daily Shorts\n✅ Long-form videos\n✅ Auto-upload to YouTube\n✅ Optimized for finance CPM\n\nFree trial → {APP_URL}",
]


def post_daily_tip(client, dry_run=False):
    tip = random.choice(DAILY_TIPS)
    print(f"Posting tip:\n{tip[:100]}...")
    if not dry_run:
        client.create_tweet(text=tip)
        print("Posted!")
    else:
        print("[DRY RUN] Would post tip.")


def post_promo(client, dry_run=False):
    tweet = random.choice(PROMO_TWEETS)
    print(f"Posting promo:\n{tweet[:100]}...")
    if not dry_run:
        client.create_tweet(text=tweet)
        print("Posted!")
    else:
        print("[DRY RUN] Would post promo.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["tip", "promo"], default="tip")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    if args.mode == "tip":
        post_daily_tip(client, dry_run=args.dry_run)
    elif args.mode == "promo":
        post_promo(client, dry_run=args.dry_run)
