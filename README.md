# Orboni for Odoo

Crypto payments for Odoo, paid straight to your own wallets: USDT, USDC, BTC, ETH, SOL, TON, TRX and more, 17 coins on 16 networks. Orboni never holds your money and never has your keys.

`payment_orboni` adds Orboni as a payment provider: on the eCommerce checkout, on orders and invoices paid from the customer portal, and on payment links. The customer pays on Orboni's payment page; a signed webhook tells Odoo, and Odoo confirms the order or reconciles the invoice as with any other provider.

## Versions

One branch per Odoo version, each with the same features:

| Odoo | Branch |
|---|---|
| 20 | [`20.0`](../../tree/20.0) |
| 19 | [`19.0`](../../tree/19.0) |
| 18 | [`18.0`](../../tree/18.0) |

## Install

1. Download the module for your Odoo version from [Odoo Apps](https://apps.odoo.com/apps/modules/20.0/payment_orboni), or copy the `payment_orboni` folder of your version's branch (or its zip from the [releases](../../releases)) into your addons path. Then update the apps list and install **Payment Provider: Orboni**.
2. In the [Orboni dashboard](https://orboni.com), add the wallets you want to be paid to, and copy a secret key (Developers → API keys) into the provider's **Secret Key**: a test key (`sk_test_…`) first.
3. Under Developers → Webhooks, add an endpoint at the **Webhook Address** the provider shows, with the `checkout.session.*` events, and paste its signing secret (`whsec_…`) into **Webhook Signing Secret**.
4. Publish the provider in test mode, pay an order with crypto and press *Simulate payment* on the payment page. Then swap in a live key and go live.

The full guide, with every transaction state and everything the module sends to Orboni: https://orboni.com/docs/odoo

## Pricing

The module is free. Orboni charges 0.5% of each completed live payment: no monthly fee, no setup fee; test payments are never billed.

## Support

support@orboni.com

## License

LGPL-3.0 (`payment_orboni/LICENSE`).
