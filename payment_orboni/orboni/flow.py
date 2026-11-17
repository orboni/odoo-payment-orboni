# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.
"""What a transaction sends to Orboni, and what a session read back means for it.

The same file in every Odoo version's module: only the hooks into Odoo's payment flow differ.
"""

import hashlib
import hmac
import re
from urllib.parse import urlencode

from . import currencies

# The events whose meaning is not in the session alone.
REVERSED = 'checkout.session.payment_reversed'
EXTRA = 'checkout.session.extra_received'
# Not Orboni's: the customer came back by the payment page's cancel link.
LEFT = 'orboni.left'

CHAIN_NAMES = {
    'tron': 'TRON', 'ethereum': 'Ethereum', 'bsc': 'BNB Chain', 'solana': 'Solana', 'ton': 'TON',
    'polygon': 'Polygon', 'base': 'Base', 'arbitrum': 'Arbitrum', 'optimism': 'Optimism',
    'avalanche': 'Avalanche', 'bitcoin': 'Bitcoin', 'litecoin': 'Litecoin', 'dogecoin': 'Dogecoin',
    'bitcoincash': 'Bitcoin Cash', 'xrp': 'XRP Ledger', 'stellar': 'Stellar',
}

RETURN_ROUTE = '/payment/orboni/return'
WEBHOOK_ROUTE = '/payment/orboni/webhook'

EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def site_key(env):
    """This database, as a short hash Orboni's events carry back (`odoo_site`): another Odoo's
    events, on the same Orboni project, are left alone."""
    params = env['ir.config_parameter'].sudo()
    get = getattr(params, 'get_str', None) or params.get_param  # get_str since Odoo 20
    secret = get('database.secret') or ''
    uuid = get('database.uuid') or ''
    return hmac.new(secret.encode(), ('orboni-site|' + uuid).encode(), hashlib.sha256).hexdigest()[:12]


def fit(text, limit):
    """At most `limit` characters, cut at a word with an ellipsis."""
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    space = cut.rfind(' ')
    if space > limit / 2:
        cut = cut[:space]
    return cut.rstrip(' ,.;:') + '…'


def session_body(tx, base_url, site, _):
    """The checkout session for one transaction: its amount, what it pays for and where the
    customer comes back to."""
    currency = tx.currency_id.name
    lines, documents, kind = _documents(tx)
    company = tx.company_id.name or ''

    if kind == 'order':
        what = _('Order %s', ', '.join(documents))
    elif kind == 'invoice':
        what = _('Invoice %s', ', '.join(documents))
    else:
        what = _('Payment %s', tx.reference)
    details = _('%(what)s at %(company)s', what=what, company=company) if company else what

    back = base_url.rstrip('/') + RETURN_ROUTE + '?' + urlencode({'ref': tx.reference})
    metadata = {'odoo_site': site, 'odoo_reference': tx.reference}
    if documents:
        metadata['odoo_documents'] = fit(', '.join(documents), 500)

    body = {
        'amount': currencies.minor(tx.amount, currency),
        'currency': currency.lower(),
        'description': fit(', '.join(lines) or what, 250),
        'details': fit(details, 500),
        'client_reference_id': fit(tx.reference, 200),
        'success_url': back + '&session_id={CHECKOUT_SESSION_ID}',
        'cancel_url': back + '&cancel=1',
        'metadata': metadata,
    }
    if tx.partner_email and EMAIL.match(tx.partner_email):
        body['customer_email'] = tx.partner_email
    locale = _locale(tx.partner_lang)
    if locale:
        body['locale'] = locale
    return body


def _documents(tx):
    """What the transaction pays for: the lines, the documents' names and their kind."""
    lines, names = [], []
    orders = tx.sale_order_ids if 'sale_order_ids' in tx._fields else None
    if orders:
        for order in orders:
            names.append(order.name)
            for line in order.order_line:
                if line.display_type or not line.product_id:
                    continue
                lines.append(_line(line.name or line.product_id.display_name, line.product_uom_qty))
        return lines, names, 'order'

    invoices = tx.invoice_ids if 'invoice_ids' in tx._fields else None
    if invoices:
        for invoice in invoices:
            names.append(invoice.name)
            for line in invoice.invoice_line_ids:
                if line.display_type != 'product':
                    continue
                lines.append(_line(line.name or line.product_id.display_name, line.quantity))
        return lines, names, 'invoice'

    return lines, names, ''


def _line(name, quantity):
    name = (name or '').strip().split('\n')[0].strip()
    quantity = float(quantity or 1)
    if quantity > 1:
        return '%s × %s' % (name, int(quantity) if quantity.is_integer() else quantity)
    return name


def _locale(lang):
    match = re.match(r'^([a-z]{2,3})(?:_([A-Z]{2}))?', lang or '')
    if not match:
        return None
    return match.group(1) + ('-' + match.group(2) if match.group(2) else '')


def ours(session, site, reference=None):
    """A session this database made, for this transaction when one is named."""
    metadata = session.get('metadata') if isinstance(session.get('metadata'), dict) else {}
    return (
        bool(re.match(r'^cs_(live|test)_[A-Za-z0-9]+$', str(session.get('id') or '')))
        and metadata.get('odoo_site') == site
        and bool(metadata.get('odoo_reference'))
        and (reference is None or metadata.get('odoo_reference') == reference)
    )


def outcome(session, event, _):
    """What the session is now, for its transaction: a target state and a note.

    `done` (paid in full), `pending` (confirming, part paid, held), `error` (closed part paid:
    money arrived that pays only part), `canceled` (ran out unpaid, or left by the cancel link
    with nothing sent), `reversed` (money that paid it left the chain), or None while the page is
    open and nothing was sent.
    """
    status = session.get('status')
    payment = session.get('payment_status')
    currency = session.get('currency') or ''
    received = currencies.format_decimal(session.get('amount_received'), currency)
    due = currencies.format_decimal(session.get('amount_due'), currency)

    if event == LEFT and status == 'open' and payment == 'unpaid':
        return 'canceled', _('The customer left the payment page.')

    if status == 'complete' and payment == 'paid':
        note = paid_note(session, _)
        if event == EXTRA:
            note = _(
                'More arrived after it was paid: %s in all; send the extra back from your wallet'
                ' if the customer asks.', received,
            ) + ' ' + note
        return 'done', note

    if status == 'expired' and payment == 'partially_paid':
        return 'error', _(
            'The payment page closed part paid: %(received)s of %(due)s arrived in your wallet.'
            ' Settle the rest with the customer.', received=received, due=due,
        )

    if event == REVERSED:
        return 'reversed', _(
            'Money that paid it left the chain (%s remains). It is confirmed again if the payment'
            ' completes again.', received,
        )

    if payment == 'processing':
        return 'pending', _('Confirming on the network.')
    if payment == 'partially_paid':
        return 'pending', _('Part paid: %(received)s of %(due)s; waiting for the rest.', received=received, due=due)
    if payment == 'held':
        return 'pending', _(
            'The money is in your wallet but held for review in the Orboni dashboard (%s). Accept it'
            ' there and the payment is confirmed.', session.get('review_reason') or '-',
        )
    if status == 'expired':
        return 'canceled', _('The payment page ran out unpaid.')
    return None, ''


def paid_note(session, _):
    payment = session.get('payment') if isinstance(session.get('payment'), dict) else {}
    currency = session.get('currency') or ''
    received = currencies.format_decimal(session.get('amount_received'), currency)
    if payment.get('coin') and payment.get('amount'):
        chain = str(payment.get('chain') or '')
        note = _(
            'Paid %(amount)s %(coin)s on %(network)s (%(worth)s).',
            amount=payment['amount'], coin=payment['coin'],
            network=CHAIN_NAMES.get(chain, chain.capitalize()), worth=received,
        )
    else:
        note = _('Paid (%s).', received)
    if not session.get('livemode'):
        note += ' ' + _('Test payment: no real money moved.')
    if session.get('paid_late'):
        note += ' ' + _('Paid after the payment page ran out.')
    return note
