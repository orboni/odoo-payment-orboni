# Part of Orboni's payment provider for Odoo. See LICENSE file for full copyright and licensing details.
"""Orboni's API, as much of it as Odoo needs: make a checkout session, read one back.

`Authorization: Bearer sk_…`, JSON both ways. The same file in every Odoo version's module.
"""

import json
import os
import re
import time

import requests

VERSION = '1.0.0'

SESSION_ID = re.compile(r'^cs_(live|test)_[A-Za-z0-9]+$')
SECRET_KEY = re.compile(r'^sk_(live|test)_[A-Za-z0-9]+$')
WEBHOOK_SECRET = re.compile(r'^whsec_[A-Za-z0-9]+$')

# Seconds Orboni's own "updating, retry" answer may make a buyer wait, once.
MAX_RETRY_AFTER = 5


class ApiError(Exception):
    """Orboni said no, or could not be reached."""

    def __init__(self, message, error_type='api_error', status=0, param=''):
        super().__init__(message)
        self.type = error_type
        self.status = status
        self.param = param


class Api:

    def __init__(self, secret, user_agent):
        self.secret = secret
        self.user_agent = user_agent
        # Another Orboni only for trying the module out (ORBONI_API_URL in Odoo's environment).
        self.base = (os.environ.get('ORBONI_API_URL') or 'https://orboni.com').rstrip('/')

    def create_session(self, body, idempotency_key):
        """A new checkout session. The key makes a retry return the session the first try made
        (`_replayed` is then true) instead of a second one."""
        return self._request('POST', '/v1/checkout/sessions', body, idempotency_key)

    def get_session(self, session_id):
        if not SESSION_ID.match(session_id or ''):
            raise ApiError('Not an Orboni checkout session id.', 'bad_session_id')
        return self._request('GET', '/v1/checkout/sessions/' + session_id)

    def _request(self, method, path, body=None, idempotency_key=None):
        headers = {
            'Authorization': 'Bearer ' + self.secret,
            'Accept': 'application/json',
            'User-Agent': self.user_agent,
        }
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        # A GET, or a POST under an idempotency key, can be sent twice safely.
        retryable = method == 'GET' or bool(idempotency_key)

        response = None
        for attempt in range(2):
            try:
                response = requests.request(
                    method,
                    self.base + path,
                    headers=headers,
                    data=json.dumps(body) if body is not None else None,
                    timeout=(10, 20),
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                if retryable and attempt == 0:
                    continue
                raise ApiError('Orboni could not be reached: %s' % error, 'connection_error') from error
            # Orboni's own deploy: a few seconds' "503, retry after".
            if response.status_code == 503 and retryable and attempt == 0:
                time.sleep(min(max(_int(response.headers.get('Retry-After'), 1), 1), MAX_RETRY_AFTER))
                continue
            break

        return _answer(response)


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _answer(response):
    try:
        data = response.json()
    except ValueError:
        data = None
    if 200 <= response.status_code < 300 and isinstance(data, dict):
        if response.headers.get('Idempotent-Replayed', '') == 'true':
            data['_replayed'] = True
        return data

    error = data.get('error') if isinstance(data, dict) and isinstance(data.get('error'), dict) else {}
    raise ApiError(
        error.get('message') if isinstance(error.get('message'), str) else 'Orboni answered HTTP %d.' % response.status_code,
        error.get('type') if isinstance(error.get('type'), str) else 'http_%d' % response.status_code,
        response.status_code,
        error.get('param') if isinstance(error.get('param'), str) else '',
    )
