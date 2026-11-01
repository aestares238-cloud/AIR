import gc
import ujson
import urequests


class APIClient:
    def __init__(self, url, api_key=""):
        self.url = url
        self.api_key = api_key

    def send(self, payload):
        """POST one reading. Returns True when the server accepted it."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        body = ujson.dumps(payload)
        response = None
        try:
            gc.collect()
            try:
                response = urequests.post(self.url, data=body, headers=headers, timeout=20)
            except TypeError:  # older urequests has no timeout argument
                response = urequests.post(self.url, data=body, headers=headers)
            ok = 200 <= response.status_code < 300
            if not ok:
                print("Server answered", response.status_code)
            return ok
        except Exception as e:
            print("HTTP Error:", e)
            return False
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
