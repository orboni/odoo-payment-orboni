# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.
"""The currencies Orboni takes a price in, and how amounts are written for it.

Amounts go in each currency's smallest unit (ISO 4217): 1250 for 12.50 EUR, 1500 for 1500 JPY.
Orboni turns a price into dollars at the rate of the day, the European Central Bank's or the
market's.
"""

from decimal import ROUND_HALF_UP, Decimal

DECIMALS = {
    'USD': 2, 'EUR': 2, 'GBP': 2, 'CHF': 2, 'PLN': 2, 'CZK': 2,
    'HUF': 2, 'RON': 2, 'DKK': 2, 'SEK': 2, 'NOK': 2, 'ISK': 0,
    'TRY': 2, 'JPY': 0, 'KRW': 0, 'CNY': 2, 'HKD': 2, 'SGD': 2,
    'INR': 2, 'IDR': 2, 'MYR': 2, 'PHP': 2, 'THB': 2, 'ILS': 2,
    'AUD': 2, 'NZD': 2, 'CAD': 2, 'MXN': 2, 'BRL': 2, 'ZAR': 2,
    'UAH': 2, 'ARS': 2, 'CLP': 0, 'AED': 2, 'SAR': 2, 'TWD': 2,
    'VND': 0,
}

# Orboni's least payment is worth $1: checked here for dollars, by Orboni in any other currency.
MIN_USD_CENTS = 100


def supports(currency):
    return (currency or '').upper() in DECIMALS


def decimals(currency):
    return DECIMALS.get((currency or '').upper(), 2)


def minor(amount, currency):
    """An amount in the currency's smallest unit."""
    return int(Decimal(str(amount)).scaleb(decimals(currency)).quantize(Decimal('1'), ROUND_HALF_UP))


def major(amount_minor, currency):
    """Back from the smallest unit: 12.5 for 1250 euro cents."""
    return float(Decimal(int(amount_minor)).scaleb(-decimals(currency)))


def format_decimal(amount, currency):
    """One of a session's decimal amounts with its currency: "25.00 EUR"."""
    places = decimals(currency)
    return '%.*f %s' % (places, float(amount or 0), (currency or '').upper())
