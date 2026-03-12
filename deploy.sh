#!/bin/bash
# ⚡ FinanceFlow — One-Click Deploy
# This script fixes git history and pushes to GitHub
# Run: bash deploy.sh

set -e

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ⚡ FinanceFlow — Auto Deploy Script          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")"

echo "📁 Working in: $(pwd)"
echo ""

# Remove any leftover save files
rm -f app.py.save *.save 2>/dev/null || true

# Wipe old git history completely (clean start)
echo "🧹 Clearing old git history..."
rm -rf .git

# Fresh git init
echo "📦 Creating fresh git repo..."
git init
git add .
git commit -m "🚀 FinanceFlow SaaS — Launch Ready"

# Set remote
git remote add origin https://github.com/cosmolotto/financeflow-saas.git
git branch -M main

echo ""
echo "🚀 Pushing to GitHub..."
echo "   (Enter your GitHub username and token when asked)"
echo ""
git push -u origin main --force

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ Pushed to GitHub successfully!            ║"
echo "║                                              ║"
echo "║  Now go to:                                  ║"
echo "║  railway.app → New Project → GitHub repo     ║"
echo "║  Select: cosmolotto/financeflow-saas          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
