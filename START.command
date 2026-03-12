#!/bin/bash
# FinanceFlow — Double-click this file to start everything!
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  💰 FinanceFlow SaaS — Starting Up...        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Install dependencies if needed
pip3 install Pillow flask --break-system-packages -q 2>/dev/null

# Kill anything on port 5001
lsof -ti:5001 | xargs kill -9 2>/dev/null
sleep 1

# Start the Flask app in background
echo "Starting app on http://localhost:5001..."
python3 app.py &
APP_PID=$!
sleep 2

# Open browser
open http://localhost:5001 2>/dev/null

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  App:   http://localhost:5001                ║"
echo "║  Admin: http://localhost:5001/admin          ║"
echo "║                                              ║"
echo "║  NOW open a NEW terminal and run:            ║"
echo "║  cd ~/Downloads/saas && python3 worker.py   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Keep terminal open
wait $APP_PID
