from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
import os, hmac, hashlib, json, urllib.request, urllib.parse, sqlite3

paddle_bp = Blueprint('paddle', __name__)

PADDLE_VENDOR_ID = os.environ.get('PADDLE_VENDOR_ID', '')
PADDLE_API_KEY = os.environ.get('PADDLE_API_KEY', '')
PADDLE_WEBHOOK_SECRET = os.environ.get('PADDLE_WEBHOOK_SECRET', '')
PADDLE_ENV = os.environ.get('PADDLE_ENV', 'sandbox')  # 'sandbox' or 'production'
PADDLE_API_BASE = 'https://api.paddle.com' if PADDLE_ENV == 'production' else 'https://sandbox-api.paddle.com'

# Map plans to Paddle price IDs (set these in Paddle dashboard, then add env vars)
PADDLE_PRICE_IDS = {
    'pro': os.environ.get('PADDLE_PRICE_PRO', ''),
    'agency': os.environ.get('PADDLE_PRICE_AGENCY', ''),
    'growth': os.environ.get('PADDLE_PRICE_GROWTH', ''),
}

PLAN_LIMITS = {
    'pro': {'channels': 3, 'videos_per_week': 14, 'custom_prompts': True, 'social_posting': True, 'autopilot': False},
    'agency': {'channels': 10, 'videos_per_week': 9999, 'custom_prompts': True, 'social_posting': True, 'autopilot': True},
    'growth': {'channels': 1, 'videos_per_week': 9999, 'custom_prompts': True, 'social_posting': True, 'autopilot': True},
}


def _get_db():
    db_path = os.environ.get('DATABASE_URL', 'financeflow.db')
    if db_path.startswith('postgres'):
        raise RuntimeError('Use psycopg2 for PostgreSQL')
    return sqlite3.connect(db_path)


def _verify_paddle_signature(payload: bytes, sig_header: str) -> bool:
    if not PADDLE_WEBHOOK_SECRET or not sig_header:
        return True  # skip verification if secret not configured
    # Paddle webhook signature format: ts=...;h1=...
    parts = dict(p.split('=', 1) for p in sig_header.split(';') if '=' in p)
    ts = parts.get('ts', '')
    h1 = parts.get('h1', '')
    signed_payload = f"{ts}:{payload.decode()}"
    expected = hmac.new(PADDLE_WEBHOOK_SECRET.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(h1, expected)


@paddle_bp.route('/api/paddle/checkout', methods=['POST'])
@login_required
def create_checkout():
    """Create a Paddle checkout session and return the transaction ID / checkout URL."""
    data = request.get_json(force=True)
    plan = data.get('plan', '').lower()
    price_id = PADDLE_PRICE_IDS.get(plan)

    if not plan or plan not in PADDLE_PRICE_IDS:
        return jsonify({'error': 'Invalid plan'}), 400
    if not PADDLE_API_KEY:
        return jsonify({'error': 'Paddle not configured'}), 503
    if not price_id:
        return jsonify({'error': f'Paddle price ID for {plan} not set. Add PADDLE_PRICE_{plan.upper()} env var.'}), 503

    payload = json.dumps({
        'items': [{'price_id': price_id, 'quantity': 1}],
        'customer': {'email': current_user.email},
        'custom_data': {'user_id': str(current_user.id), 'plan': plan},
    }).encode()

    req = urllib.request.Request(
        f'{PADDLE_API_BASE}/transactions',
        data=payload,
        headers={
            'Authorization': f'Bearer {PADDLE_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        checkout_url = result.get('data', {}).get('checkout', {}).get('url', '')
        transaction_id = result.get('data', {}).get('id', '')
        return jsonify({'checkout_url': checkout_url, 'transaction_id': transaction_id})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return jsonify({'error': f'Paddle API error: {body}'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@paddle_bp.route('/webhook/paddle', methods=['POST'])
def paddle_webhook():
    """Handle Paddle webhook events to activate subscriptions."""
    payload = request.get_data()
    sig_header = request.headers.get('Paddle-Signature', '')

    if not _verify_paddle_signature(payload, sig_header):
        return jsonify({'error': 'Invalid signature'}), 400

    try:
        data = json.loads(payload)
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    event_type = data.get('event_type', '')
    event_data = data.get('data', {})

    if event_type in ('transaction.completed', 'subscription.activated', 'subscription.updated'):
        custom_data = event_data.get('custom_data') or {}
        user_id = custom_data.get('user_id')
        plan = custom_data.get('plan')

        if user_id and plan and plan in PLAN_LIMITS:
            limits = PLAN_LIMITS[plan]
            try:
                db = _get_db()
                cur = db.cursor()
                cur.execute(
                    """UPDATE users SET plan=?, channels_limit=?, videos_per_week=?,
                       custom_prompts=?, social_posting=?, autopilot=?
                       WHERE id=?""",
                    (plan, limits['channels'], limits['videos_per_week'],
                     1 if limits['custom_prompts'] else 0,
                     1 if limits['social_posting'] else 0,
                     1 if limits['autopilot'] else 0,
                     int(user_id))
                )
                db.commit()
                db.close()
                # Record payment
                db2 = _get_db()
                cur2 = db2.cursor()
                cur2.execute(
                    "INSERT INTO payments (user_id, plan, method, reference, status) VALUES (?,?,?,?,?)",
                    (int(user_id), plan, 'paddle', event_data.get('id', ''), 'approved')
                )
                db2.commit()
                db2.close()
            except Exception as e:
                current_app.logger.error(f'[Paddle webhook] DB error: {e}')

    elif event_type in ('subscription.canceled', 'subscription.paused'):
        custom_data = event_data.get('custom_data') or {}
        user_id = custom_data.get('user_id')
        if user_id:
            try:
                db = _get_db()
                cur = db.cursor()
                cur.execute(
                    "UPDATE users SET plan='starter', channels_limit=1, videos_per_week=3, custom_prompts=0, social_posting=0, autopilot=0 WHERE id=?",
                    (int(user_id),)
                )
                db.commit()
                db.close()
            except Exception as e:
                current_app.logger.error(f'[Paddle webhook] cancel DB error: {e}')

    return jsonify({'status': 'ok'})


@paddle_bp.route('/api/paddle/status')
def paddle_status():
    """Check if Paddle is configured (used by frontend)."""
    configured = bool(PADDLE_API_KEY and PADDLE_VENDOR_ID)
    return jsonify({
        'configured': configured,
        'env': PADDLE_ENV,
        'prices': {k: bool(v) for k, v in PADDLE_PRICE_IDS.items()},
    })
