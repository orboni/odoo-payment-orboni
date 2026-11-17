# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging

from werkzeug.exceptions import BadRequest, ServiceUnavailable

from odoo import http
from odoo.http import request

from odoo.addons.payment_orboni.orboni import flow, signature
from odoo.addons.payment_orboni.orboni.api import ApiError

_logger = logging.getLogger(__name__)


class OrboniController(http.Controller):

    @http.route(
        flow.RETURN_ROUTE, type='http', auth='public', methods=['GET'], csrf=False,
        save_session=False,
    )
    def orboni_return(self, ref=None, cancel=None, **kwargs):
        """ The customer back from the payment page: paid (`session_id`) or by its cancel link
        (`cancel`). The session is read back from Orboni and the transaction moved to what it
        says, then the customer sees Odoo's payment status page.

        The route keeps no session of its own (`save_session`): the status page finds the
        customer's transaction in the browser's session.
        """
        tx_sudo = self._orboni_transaction(ref)
        if tx_sudo and tx_sudo.provider_reference:
            try:
                session = tx_sudo.provider_id._orboni_api().get_session(tx_sudo.provider_reference)
            except ApiError as error:
                # The webhook records it once Orboni answers again.
                _logger.warning("Orboni did not answer for %s: %s", tx_sudo.reference, error)
                session = None
            if session and flow.ours(session, flow.site_key(request.env), tx_sudo.reference):
                tx_sudo._orboni_record(session, flow.LEFT if cancel else '')
        return request.redirect('/payment/status')

    @http.route(
        flow.WEBHOOK_ROUTE, type='http', auth='public', methods=['POST'], csrf=False,
        save_session=False,
    )
    def orboni_webhook(self, **kwargs):
        """ Orboni's signed event. A session's event is read back from Orboni before anything
        moves; another site's event, or one that is not a session's, is acknowledged and left.

        :raise BadRequest: The signature does not match: Orboni sends it again, and its dashboard
                           shows the failed deliveries.
        :raise ServiceUnavailable: Orboni could not be reached to read the session back: it sends
                                   the event again.
        """
        raw = request.httprequest.get_data()
        try:
            event = json.loads(raw)
        except ValueError:
            raise BadRequest() from None
        data = event.get('data') if isinstance(event, dict) else None
        session_data = data.get('object') if isinstance(data, dict) else None
        kind = event.get('type') if isinstance(event, dict) else None
        if not isinstance(session_data, dict) or not isinstance(kind, str) or not kind.startswith('checkout.session.'):
            return ''  # Not a payment's: Orboni sends a project's every event to every endpoint.

        site = flow.site_key(request.env)
        metadata = session_data.get('metadata') if isinstance(session_data.get('metadata'), dict) else {}
        if metadata.get('odoo_site') != site:
            return ''  # Another site's, on the same Orboni project.
        tx_sudo = self._orboni_transaction(metadata.get('odoo_reference'))
        if not tx_sudo:
            return ''

        header = request.httprequest.headers.get('Webhook-Signature', '')
        if not signature.verify(tx_sudo.provider_id._orboni_webhook_secret(), raw, header):
            _logger.warning("Orboni webhook for %s refused: its signature does not match.", tx_sudo.reference)
            raise BadRequest()

        try:
            session = tx_sudo.provider_id._orboni_api().get_session(str(session_data.get('id') or ''))
        except ApiError as error:
            _logger.warning("Orboni did not answer for %s: %s", tx_sudo.reference, error)
            raise ServiceUnavailable() from error
        if flow.ours(session, site, tx_sudo.reference):
            _logger.info(
                "Orboni %s: session %s is %s, %s.",
                kind, session.get('id'), session.get('status'), session.get('payment_status'),
            )
            tx_sudo._orboni_record(session, kind)
        return ''

    @staticmethod
    def _orboni_transaction(reference):
        if not isinstance(reference, str) or not reference:
            return request.env['payment.transaction'].sudo()
        return request.env['payment.transaction'].sudo().search(
            [('reference', '=', reference), ('provider_code', '=', 'orboni')], limit=1
        )
