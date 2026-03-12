#!/bin/bash
# FinanceFlow — Clean Git Push Script
# Run: bash push_to_github.sh

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  🚀 FinanceFlow — Pushing to GitHub       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

cd ~/Downloads/saas

# Remove any leftover .git to start clean
echo "🧹 Cleaning old git history..."
rm -rf .git

# Fresh init
echo "📦 Initializing fresh repo..."
git init
git add .
git commit -m "🚀 FinanceFlow SaaS — Launch (secrets in env vars)"
git remote add origin https://github.com/cosmolotto/financeflow-saas.git
git branch -M main

echo ""
echo "⬆️  Pushing to GitHub..."
echo "   (Enter your GitHub username & Personal Access Token when asked)"
echo ""

git push -u origin main --force

echo ""
echo "✅ Done! Now go deploy on Railway:"
echo "   1. railway.app → New Project → Deploy from GitHub"
echo "   2. Select: cosmolotto/financeflow-saas"
echo "   3. Settings → Variables → add your secrets (see RAILWAY_VARS.txt)"
echo ""
