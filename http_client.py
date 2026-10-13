import requests


def get_json(url, params=None, headers=None, timeout=30):
    """Perform a GET and return (status_code, parsed_json)."""
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    return response.status_code, response.json()
