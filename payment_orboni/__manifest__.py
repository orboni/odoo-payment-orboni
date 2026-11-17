# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: Orboni",
    'version': '20.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "Crypto payments (USDT, USDC, BTC, ETH and more) straight to your own wallets.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'author': "Orboni",
    'website': "https://orboni.com",
    'support': "support@orboni.com",
    'depends': ['payment'],
    'data': [
        'views/payment_orboni_templates.xml',
        'views/payment_provider_views.xml',

        'data/payment_provider_data.xml',
        'data/payment_method_data.xml',
    ],
    'images': ['static/description/banner.png'],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
}
