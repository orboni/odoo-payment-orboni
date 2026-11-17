# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, release
from odoo.exceptions import ValidationError

from odoo.addons.payment_orboni.orboni import api as orboni_api
from odoo.addons.payment_orboni.orboni import currencies, flow


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('orboni', "Orboni")], ondelete={'orboni': 'set default'}
    )
    orboni_secret_key = fields.Char(
        string="Orboni Secret Key",
        help="In the Orboni dashboard, Developers → API keys: a test key (sk_test_…) in Test Mode,"
             " a live key (sk_live_…) once Enabled.",
        required_if_provider='orboni',
        copy=False,
        groups='base.group_system',
    )
    orboni_webhook_secret = fields.Char(
        string="Orboni Webhook Signing Secret",
        help="The signing secret (whsec_…) of the endpoint added under Developers → Webhooks in the"
             " Orboni dashboard, at the webhook address below.",
        required_if_provider='orboni',
        copy=False,
        groups='base.group_system',
    )
    orboni_webhook_url = fields.Char(
        string="Orboni Webhook Address", compute='_compute_orboni_webhook_url'
    )

    # === COMPUTE METHODS === #

    def _compute_orboni_webhook_url(self):
        for provider in self:
            provider.orboni_webhook_url = provider.get_base_url().rstrip('/') + flow.WEBHOOK_ROUTE

    def _get_supported_currencies(self):
        """ Override of `payment` to return the currencies Orboni takes a price in. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'orboni':
            supported_currencies = supported_currencies.filtered(
                lambda c: currencies.supports(c.name)
            )
        return supported_currencies

    # === CONSTRAINT METHODS === #

    @api.constrains('code', 'state', 'orboni_secret_key', 'orboni_webhook_secret')
    def _check_orboni_credentials(self):
        """ The key decides test or live at Orboni, so it must agree with the provider's state:
        a test key in Test Mode, a live key once Enabled. """
        for provider in self.sudo().filtered(lambda p: p.code == 'orboni' and p.state != 'disabled'):
            key = (provider.orboni_secret_key or '').strip()
            if not orboni_api.SECRET_KEY.match(key):
                raise ValidationError(self.env._("Enter an Orboni secret key: sk_live_… or sk_test_…."))
            if provider.state == 'test' and not key.startswith('sk_test_'):
                raise ValidationError(self.env._(
                    "Test Mode takes a test key (sk_test_…): a live key would take real money."
                ))
            if provider.state == 'enabled' and not key.startswith('sk_live_'):
                raise ValidationError(self.env._(
                    "Enabled takes a live key (sk_live_…): a test key takes no real money."
                ))
            if not orboni_api.WEBHOOK_SECRET.match((provider.orboni_webhook_secret or '').strip()):
                raise ValidationError(self.env._(
                    "Enter the webhook endpoint's signing secret: whsec_…."
                ))

    # === CRUD METHODS === #

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'orboni':
            return super()._get_default_payment_method_codes()
        return {'orboni'}

    # === BUSINESS METHODS === #

    def _orboni_api(self):
        """ Orboni's API with this provider's key. """
        self.ensure_one()
        return orboni_api.Api(
            (self.sudo().orboni_secret_key or '').strip(),
            'orboni-odoo/%s; Odoo/%s' % (orboni_api.VERSION, release.version),
        )

    def _orboni_webhook_secret(self):
        self.ensure_one()
        return (self.sudo().orboni_webhook_secret or '').strip()
