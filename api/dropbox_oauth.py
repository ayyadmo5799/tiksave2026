"""
POST /api/token
Body: { app_key, app_secret, code, redirect_uri }
Returns: { refresh_token, access_token }
"""
import json
import requests
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        app_key      = body.get("app_key",      "").strip()
        app_secret   = body.get("app_secret",   "").strip()
        code         = body.get("code",         "").strip()
        redirect_uri = body.get("redirect_uri", "").strip()

        if not all([app_key, app_secret, code]):
            self._respond(400, {"error": "app_key, app_secret, code مطلوبة"})
            return

        try:
            r = requests.post(
                "https://api.dropbox.com/oauth2/token",
                data={
                    "code":         code,
                    "grant_type":   "authorization_code",
                    "redirect_uri": redirect_uri,
                    "client_id":    app_key,
                    "client_secret": app_secret,
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            self._respond(200, {
                "refresh_token": data.get("refresh_token", ""),
                "access_token":  data.get("access_token",  ""),
            })
        except requests.HTTPError as e:
            self._respond(e.response.status_code,
                          {"error": e.response.text[:300]})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
