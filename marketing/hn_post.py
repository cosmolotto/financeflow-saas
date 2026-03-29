"""
FinanceFlow — Hacker News "Show HN" submission helper.
Generates the Show HN post and optionally opens the submission URL in browser.

HN doesn't have a public posting API — this opens the submission page pre-filled.
Run this once when ready to launch on HN.

Usage:
  python hn_post.py --open
  python hn_post.py --print
"""

import argparse
import urllib.parse
import webbrowser

APP_URL = "https://vercel-financeflow.vercel.app"
GITHUB_URL = "https://github.com/cosmolotto/financeflow-saas"

TITLE = "Show HN: FinanceFlow – AI that generates and uploads YouTube finance videos automatically"

TEXT = """I've been building this for a few months and finally feel like it's worth sharing.

FinanceFlow takes a niche + video type, generates a script with AI, synthesizes a voiceover, renders the video with animated charts using FFmpeg, and uploads it directly to YouTube — all automatically.

The motivation: finance YouTube channels earn $8-25 CPM (vs $1-3 for entertainment), but the one thing that kills most creators is consistency. Posting daily is brutal if you're doing it manually.

Technical stack:
- Flask + SQLite for the backend (Render.com)
- OpenAI GPT-4o-mini for finance-specific script generation
- ElevenLabs or Edge TTS for voiceover synthesis (falls back gracefully if no API key)
- FFmpeg for video rendering at 24fps with animated chart overlays
- YouTube Data API for upload + thumbnail generation
- Celery/Redis for async job processing (falls back to threading without Redis)

What I'm most happy with:
1. The validation layer — before any strategy goes live, the bot runs Walk-Forward analysis and Monte Carlo simulation. Most bots just backtest, which leads to overfit results.
2. The fallback design — every expensive dependency (OpenAI, ElevenLabs, Redis, Celery) has a graceful fallback so the app works even without API keys configured.
3. The 4-pass validation before live trading (for the AlgoTrading module).

Current limitations:
- YouTube OAuth setup requires manual credentials (can't automate this fully)
- Video quality is functional but not "Netflix-level" — I'm using stock footage-style chart animations
- Paper trading mode works; live trading is in beta

Live demo: {url}
GitHub: {github}

Happy to answer questions on the video generation pipeline, the FFmpeg rendering approach, or the Walk-Forward validation logic.""".format(
    url=APP_URL, github=GITHUB_URL
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true", help="Open HN submission in browser")
    parser.add_argument("--print", action="store_true", help="Print the post text")
    args = parser.parse_args()

    params = urllib.parse.urlencode({"title": TITLE, "url": APP_URL, "text": TEXT})
    hn_url = f"https://news.ycombinator.com/submitlink?{params}"

    if args.print or not args.open:
        print("=== HACKER NEWS SHOW HN ===")
        print(f"Title: {TITLE}")
        print(f"URL: {APP_URL}")
        print(f"\nText:\n{TEXT}")
        print(f"\nSubmission URL:\n{hn_url}")

    if args.open:
        print("Opening HN submission in browser...")
        webbrowser.open(hn_url)


if __name__ == "__main__":
    main()
