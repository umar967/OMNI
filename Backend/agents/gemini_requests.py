"""One bounded retry policy shared by Gemini evaluations and browser decisions."""
import json
import os
import re
import time
from contextvars import ContextVar

import httpx
from google import genai
from google.genai import types

status_callback = ContextVar('gemini_status', default=None)


class ModelRequestError(RuntimeError):
    """Safe to show in the UI; never includes API response bodies or credentials."""


class GeminiRequestError(ModelRequestError):
    pass


def notify(message):
    callback = status_callback.get()
    if callback:
        callback(message)
    else:
        print(message, flush=True)


def generate_json(contents, schema=None, decision=False):
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        raise GeminiRequestError('GEMINI_API_KEY is not configured. Add it to Backend/.env and restart.')
    setting = 'GEMINI_ACTION_TIMEOUT_SECONDS' if decision else 'GEMINI_REVIEW_TIMEOUT_SECONDS'
    timeout = max(1, min(120, float(os.getenv(setting, '30' if decision else '60'))))
    attempts = max(1, min(3, int(os.getenv('GEMINI_MAX_ATTEMPTS', '2'))))
    options = types.HttpOptions(timeout=int(timeout * 1000),
                                retry_options=types.HttpRetryOptions(attempts=1))
    with genai.Client(api_key=key, http_options=options) as client:
        for attempt in range(attempts):
            notify(f'Gemini request {attempt + 1}/{attempts}; timeout {timeout:g}s.')
            try:
                response = client.models.generate_content(
                    model=os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'), contents=contents,
                    config=types.GenerateContentConfig(response_mime_type='application/json',
                                                       response_schema=schema, temperature=0.2))
                result = json.loads(response.text)
                if not isinstance(result, dict):
                    raise ValueError('Expected a JSON object')
                return result
            except Exception as exc:
                code = getattr(exc, 'code', None)
                if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
                    cause = f'Gemini timed out waiting for a response (request timeout {timeout:g}s)'
                elif isinstance(exc, httpx.TransportError):
                    cause = 'Could not connect reliably to Gemini (network or TLS connection error)'
                else:
                    cause = f'Gemini returned HTTP {code}'
                transient = isinstance(exc, (httpx.TransportError, TimeoutError)) or code in (408, 429, 500, 502, 503, 504)
                if not transient:
                    raise GeminiRequestError('Gemini rejected the request or returned invalid JSON. Check the model and API configuration.') from exc
                delay = 2.0 * (attempt + 1)
                if code == 429:
                    # Respect server retry hints, but never park a browser for minutes.
                    response = getattr(exc, 'response', None)
                    header = getattr(response, 'headers', {}).get('retry-after', '')
                    match = re.search(r'retry(?:Delay| in)\D*(\d+(?:\.\d+)?)\s*s', str(exc), re.I)
                    hint = float(header) if re.fullmatch(r'\d+(?:\.\d+)?', str(header)) else float(match.group(1)) if match else None
                    if hint is None or hint > 10:
                        raise GeminiRequestError('Gemini quota reached. Stopped without a long wait; recorded interactions are preserved. Check quota in AI Studio before retrying.') from exc
                    delay = max(delay, hint)
                if attempt + 1 >= attempts:
                    raise GeminiRequestError(f'{cause} after {attempts} attempts. Any recorded interactions are preserved. Check connectivity and model availability before retrying.') from exc
                notify(f'{cause}; retrying in {delay:g}s.')
                time.sleep(delay)
