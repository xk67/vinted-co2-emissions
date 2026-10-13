import http_client


class AuthError(RuntimeError):
    """Raised when the Vinted access token is missing or expired."""


class VintedClient:
    def __init__(self, config):
        self.base_url = config["vinted_base_url"].rstrip("/")
        self.headers = {
            "User-Agent": config["vinted_user_agent"],
            "Accept": "application/json,text/plain,*/*",
            "Cookie": config["cookie"],
        }

    def _get(self, path, **params):
        status, data = http_client.get_json(
            self.base_url + path, params=params, headers=self.headers, timeout=30
        )
        if status == 401:
            raise AuthError(
                "Vinted returned 401 UNAUTHORIZED - the access token has expired. "
                "Refresh config.local.json (or VINTED_COOKIE) with a fresh cookie."
            )
        if status >= 400:
            raise RuntimeError(f"Vinted request failed ({status}): {data}")
        return data

    def fetch_orders(self):
        """Return (orders, pagination) for all orders.

        The first request discovers ``total_entries``; the second requests
        exactly that many per page so the whole history is returned at once.
        """
        first = self._get("/api/v2/my_orders", per_page=1)
        total = first.get("pagination", {}).get("total_entries", 1) or 1
        data = self._get("/api/v2/my_orders", per_page=total)
        return data.get("my_orders", []), data.get("pagination", {})

    def fetch_conversation(self, conversation_id):
        data = self._get(f"/api/v2/conversations/{conversation_id}")
        return data.get("conversation", {})
