# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.exceptions import ValidationError

from odoo.addons.payment_orboni.orboni import currencies, transaction


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to open the transaction's checkout session and send the customer
        to its payment page.

        Note: self.ensure_one() from `_get_processing_values`

        :raise ValidationError: No payment page: the customer sees why on the checkout page.
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'orboni':
            return res

        session = transaction.open_session(self)
        if not session:
            raise ValidationError(self.state_message)
        return {'api_url': session['url']}

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of `payment` to find the transaction a session was made for.

        :raise ValidationError: No transaction has the session's reference.
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'orboni' or len(tx) == 1:
            return tx

        metadata = notification_data.get('metadata')
        reference = metadata.get('odoo_reference') if isinstance(metadata, dict) else None
        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'orboni')])
        if not tx:
            raise ValidationError("Orboni: " + self.env._(
                "No transaction found matching reference %s.", reference
            ))
        return tx

    def _process_notification_data(self, notification_data):
        """ Override of `payment` to move the transaction to what its session says, once its
        amount and currency are the transaction's.

        Note: self.ensure_one()
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'orboni':
            return

        currency = str(notification_data.get('currency') or '').upper()
        amount = int(notification_data.get('amount_total') or 0)
        if currency != self.currency_id.name or amount != currencies.minor(self.amount, currency):
            self._set_error(self.env._(
                "The amount from the payment data doesn't match the one from the transaction."
            ))
            return
        transaction.apply(self, notification_data, notification_data.get('orboni_event') or '')

    def _orboni_record(self, session, event):
        """ A session read back from Orboni, through Odoo's own entry point for payment data. """
        self.ensure_one()
        self.env['payment.transaction']._handle_notification_data(
            'orboni', dict(session, orboni_event=event)
        )
