from flask import Blueprint, request, jsonify, redirect
from flask_login import login_required, current_user
import os, hmac, hashlib, json

ls_bp = Blueprint('payments', __name__)

PLANS = {
    'starter': {'name': 'Starter', 'price': 999, 'videos': 5, 'channels': 1},
    'pro': {'name': 'Pro', 'price': 2999, 'videos': 30, 'channels': 3},
    'business': {'name': 'Business', 'price': 7999, 'videos': 9999, 'channels': 10},
}

@ls_bp.route('/pricing')
def pricing():
    return '''<!DOCTYPE html><html><head><title>FinanceFlow Pricing</title>
    <style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui;background:#0a0a0c;color:#e8e6e3}
    .container{max-width:900px;margin:0 auto;padding:4rem 2rem;text-align:center}
    h1{font-size:2.5rem;margin-bottom:0.5rem}p.sub{color:#7a7872;margin-bottom:3rem}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1.5rem}
    .card{background:#111114;border:1px solid #222228;padding:2rem;border-radius:12px}
    .card.featured{border-color:#c8ff00}
    .card h3{font-size:1.3rem;margin-bottom:0.5rem}
    .price{font-size:2.5rem;color:#c8ff00;margin:1rem 0}
    .price span{font-size:0.9rem;color:#7a7872}
    .features{list-style:none;text-align:left;margin:1.5rem 0}
    .features li{padding:0.4rem 0;color:#7a7872;font-size:0.9rem}
    .features li::before{content:"→ ";color:#c8ff00}
    .btn{display:block;width:100%;padding:0.8rem;background:#c8ff00;color:#0a0a0c;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;border-radius:6px;text-transform:uppercase;letter-spacing:0.05em}
    </style></head><body><div class="container">
    <h1>Choose Your Plan</h1><p class="sub">Start creating AI-powered finance videos today</p>
    <div class="grid">
    <div class="card"><h3>Starter</h3><div class="price">$9.99<span>/mo</span></div>
    <ul class="features"><li>5 videos/month</li><li>1 YouTube channel</li><li>Standard voice</li><li>Email support</li></ul>
    <button class="btn" onclick="alert('Lemon Squeezy checkout coming — add your variant ID')">Get Started</button></div>
    <div class="card featured"><h3>Pro</h3><div class="price">$29.99<span>/mo</span></div>
    <ul class="features"><li>30 videos/month</li><li>3 YouTube channels</li><li>ElevenLabs AI voice</li><li>Priority support</li><li>Custom thumbnails</li></ul>
    <button class="btn" onclick="alert('Lemon Squeezy checkout coming — add your variant ID')">Get Started</button></div>
    <div class="card"><h3>Business</h3><div class="price">$79.99<span>/mo</span></div>
    <ul class="features"><li>Unlimited videos</li><li>10 YouTube channels</li><li>Premium voices</li><li>Priority support</li><li>Analytics dashboard</li><li>API access</li></ul>
    <button class="btn" onclick="alert('Lemon Squeezy checkout coming — add your variant ID')">Get Started</button></div>
    </div></div></body></html>'''

@ls_bp.route('/webhook/lemonsqueezy', methods=['POST'])
def ls_webhook():
    payload = request.get_data()
    sig = request.headers.get('X-Signature', '')
    secret = os.environ.get('LEMONSQUEEZY_WEBHOOK_SECRET', '')
    if secret:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return jsonify({'error': 'Invalid signature'}), 400
    data = json.loads(payload)
    event = data.get('meta', {}).get('event_name', '')
    print(f"[LemonSqueezy] Event: {event}")
    return jsonify({'status': 'ok'})
