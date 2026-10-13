import json

import requests


class HttpError(RuntimeError):
    """Raised when a request fails or does not return valid JSON."""


def get(url, params=None, headers=None, timeout=30):
    """Perform a GET and return (status_code, body_text)."""
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    return response.status_code, response.text


def get_json(url, params=None, headers=None, timeout=30):
    """Perform a GET and return (status_code, parsed_json).

    Raises HttpError with the response body when the server does not return
    JSON (e.g. an HTML error or rate-limit page), instead of leaking a raw
    JSONDecodeError.
    """
    status, text = get(url, params=params, headers=headers, timeout=timeout)
    try:
        return status, json.loads(text)
    except ValueError as error:
        snippet = " ".join(text.split())[:200]
        raise HttpError(
            f"GET {url} returned non-JSON (HTTP {status}): {snippet!r}"
        ) from error
