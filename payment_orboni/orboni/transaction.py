# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.
"""A transaction's checkout session, and the transaction moved to what its session says.

The same file in every Odoo version's module: it uses only what Odoo 18 to 20 share
(`_set_done`, `_set_pending`, `_set_canceled`, `_set_error`, `_log_message_on_linked_documents`).
"""

import hashlib
import logging
import time

from . import currencies, flow
from .api import ApiError

_logger = logging.getLogger(__name__)

# Tries of the idempotency key: a page that ran out moves on to the next one.
MAX_TRIES = 10

# A page found open under the key is reused only with this much time left.
REUSE_MIN_SECONDS = 300


def open_session(tx):
    """The session to send the customer to, or None with the transaction in error."""
    _ = tx.env._
    currency = tx.currency_id.name
    if not currencies.supports(currency):
        tx._set_error(_("Crypto payments are not taken in %s.", currency))
        return None
    if currency == 'USD' and currencies.minor(tx.amount, currency) < currencies.MIN_USD_CENTS:
        tx._set_error(_("This payment is below the minimum for a crypto payment ($1)."))
        return None

    provider = tx.provider_id
    site = flow.site_key(tx.env)
    body = flow.session_body(tx, provider.get_base_url(), site, _)
    key = 'odoo-%s-%s' % (site, hashlib.sha256(tx.reference.encode()).hexdigest()[:24])

    try:
        session = _open(provider._orboni_api(), body, key)
    except ApiError as error:
        _logger.warning(
            "Orboni refused a payment page for %s (%s): %s", tx.reference, error.type, error
        )
        if error.type == 'amount_too_small' or (
            error.type == 'invalid_request_error' and error.param == 'amount'
        ):
            tx._set_error(_("This payment is below the minimum for a crypto payment ($1)."))
        else:
            tx._set_error(_(
                "Crypto payment is not available right now. Please try again in a minute or choose"
                " another payment method."
            ))
        return None

    tx.provider_reference = session['id']
    _logger.info("Orboni session %s for %s.", session['id'], tx.reference)
    return session


def _open(api, body, key):
    for attempt in range(1, MAX_TRIES + 1):
        try:
            session = api.create_session(body, '%s-%d' % (key, attempt))
        except ApiError as error:
            if error.type == 'idempotency_error' and error.status == 400:
                continue  # Sent before with other details (the customer's language, a new line).
            raise

        if session.get('_replayed'):
            session = api.get_session(str(session.get('id') or ''))
            if session.get('status') == 'complete' or (
                session.get('status') == 'open' and session.get('payment_status') != 'unpaid'
            ):
                return session  # Paid, or money is on its way: its page says how far it got.
            if session.get('status') != 'open' or int(session.get('expires_at') or 0) <= time.time() + REUSE_MIN_SECONDS:
                continue

        if session.get('status') == 'open' and session.get('url') and session.get('id'):
            return session

    raise ApiError('No open payment page after %d tries.' % MAX_TRIES, 'no_open_session')


def apply(tx, session, event):
    """Move the transaction to what the session (read back from Orboni) says it is now."""
    _ = tx.env._
    target, note = flow.outcome(session, event, _)
    current = session.get('id') == tx.provider_reference or not tx.provider_reference

    if target == 'done':
        if tx.state == 'done':
            if event == flow.EXTRA:
                tx._log_message_on_linked_documents(note)
            return
        # A page left (canceled) and paid later anyway, or paid after it ran out, still counts.
        tx.provider_reference = session['id']
        tx._set_done(state_message=note, extra_allowed_states=('cancel',))
    elif target == 'pending':
        tx.provider_reference = session['id']
        tx._set_pending(state_message=note, extra_allowed_states=('pending', 'cancel'))
    elif target == 'error':
        tx.provider_reference = session['id']
        tx._set_error(note, extra_allowed_states=('cancel',))
    elif target == 'reversed':
        if tx.state == 'done':
            # Odoo keeps a confirmed payment confirmed: say so where the merchant looks.
            _logger.warning("Orboni: money that paid %s left the chain.", tx.reference)
            tx._log_message_on_linked_documents(note + ' ' + _("It stays paid in Odoo: check what it was for."))
        else:
            tx._set_pending(state_message=note, extra_allowed_states=('pending', 'cancel'))
    elif target == 'canceled' and current:
        tx._set_canceled(state_message=note)
