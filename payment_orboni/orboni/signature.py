# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.
"""`Webhook-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">`, the scheme Stripe uses.

After a secret is rolled Orboni signs with both for a while, so any `v1` may match.
"""

import hashlib
import hmac
import time

# Seconds a signature stays good: an old event replayed later is refused.
TOLERANCE = 300


def verify(secret, body, header, now=None):
    """Whether `header` signs `body` (bytes) with `secret`, within the tolerance."""
    if not secret or not header:
        return False

    parts = {}
    for pair in header.split(','):
        key, _sep, value = pair.strip().partition('=')
        if _sep:
            parts.setdefault(key, []).append(value)

    try:
        timestamp = int(parts.get('t', ['0'])[0])
    except ValueError:
        return False
    now = int(time.time()) if now is None else now
    if timestamp <= 0 or abs(now - timestamp) > TOLERANCE:
        return False

    expected = hmac.new(secret.encode(), b'%d.' % timestamp + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in parts.get('v1', []))
