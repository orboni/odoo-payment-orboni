# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models

from odoo.addons.payment_orboni.orboni import currencies, transaction


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to open the transaction's checkout session and send the customer
        to its payment page.

        Note: self.ensure_one() from `_get_processing_values`
        """
        if self.provider_code != 'orboni':
            return super()._get_specific_rendering_values(processing_values)

        session = transaction.open_session(self)
        if not session:
            return {}
        return {'api_url': session['url']}

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction a session was made for. """
        if provider_code != 'orboni':
            return super()._extract_reference(provider_code, payment_data)
        metadata = payment_data.get('metadata')
        return metadata.get('odoo_reference') if isinstance(metadata, dict) else None

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to check the session's amount and currency against the
        transaction's. """
        if self.provider_code != 'orboni':
            return super()._extract_amount_data(payment_data)
        currency = str(payment_data.get('currency') or '')
        return {
            'amount': currencies.major(payment_data.get('amount_total') or 0, currency),
            'currency_code': currency.upper(),
            'precision_digits': currencies.decimals(currency),
        }

    def _apply_updates(self, payment_data):
        """ Override of `payment` to move the transaction to what its session says. """
        if self.provider_code != 'orboni':
            return super()._apply_updates(payment_data)
        transaction.apply(self, payment_data, payment_data.get('orboni_event') or '')

    def _orboni_record(self, session, event):
        """ A session read back from Orboni, through Odoo's own entry point for payment data: queued
        for the processing cron, which moves the transaction and post-processes it. """
        self.ensure_one()
        self._record(dict(session, orboni_event=event))
