"""
GET  /api/settings?pin=XXXX        → returns saved config
POST /api/settings                 → body: { pin, config }  → saves config
DELETE /api/settings?pin=XXXX      → deletes config

Uses Vercel KV (Redis) via REST API with env vars:
  KV_REST_API_URL
  KV_REST_API_TOKEN
"""
import os, json, hashlib, requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── Vercel KV helpers ──────────────────────────────────────────
def kv_url():
    return os.environ.get("KV_REST_API_URL", "").rstrip("/")

def kv_token():
    return os.environ.get("KV_REST_API_TOKEN", "")

def kv_key(pin):
    """Hash the PIN so the actual PIN is never stored"""
    return "cfg:" + hashlib.sha256(pin.encode()).hexdigest()[:32]

def kv_get(pin):
    url   = kv_url()
    token = kv_token()
    if not url or not token:
        raise RuntimeError("KV not configured")
    r = requests.get(
        f"{url}/get/{kv_key(pin)}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5
    )
    r.raise_for_status()
    data = r.json()
    return data.get("result")   # None if not found

def kv_set(pin, value_str):
    url   = kv_url()
    token = kv_token()
    if not url or not token:
        raise RuntimeError("KV not configured")
    r = requests.post(
        f"{url}/set/{kv_key(pin)}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json"
        },
        json={"value": value_str},
        timeout=5
    )
    r.raise_for_status()
    return r.json()

def kv_delete(pin):
    url   = kv_url()
    token = kv_token()
    if not url or not token:
        raise RuntimeError("KV not configured")
    r = requests.post(
        f"{url}/del/{kv_key(pin)}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5
    )
    r.raise_for_status()

def kv_available():
    return bool(kv_url() and kv_token())


# ── Handler ───────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    # ── GET — load config ──
    def do_GET(self):
        qs  = parse_qs(urlparse(self.path).query)
        pin = (qs.get("pin", [""])[0]).strip()

        if not kv_available():
            self._respond(503, {"error": "kv_not_configured",
                                "msg": "أضف KV_REST_API_URL و KV_REST_API_TOKEN في Vercel Environment Variables"})
            return

        if not pin:
            self._respond(400, {"error": "PIN مطلوب"}); return

        if len(pin) < 4:
            self._respond(400, {"error": "PIN لازم يكون 4 أرقام على الأقل"}); return

        try:
            raw = kv_get(pin)
            if raw is None:
                self._respond(404, {"error": "no_config",
                                    "msg": "لا توجد إعدادات محفوظة لهذا PIN"})
                return
            config = json.loads(raw)
            self._respond(200, {"ok": True, "config": config})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    # ── POST — save config ──
    def do_POST(self):
        if not kv_available():
            self._respond(503, {"error": "kv_not_configured"}); return

        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        pin    = str(body.get("pin", "")).strip()
        config = body.get("config", {})

        if not pin or len(pin) < 4:
            self._respond(400, {"error": "PIN لازم يكون 4 أرقام على الأقل"}); return

        if not config:
            self._respond(400, {"error": "config فارغ"}); return

        try:
            kv_set(pin, json.dumps(config, ensure_ascii=False))
            self._respond(200, {"ok": True, "msg": "تم الحفظ ✅"})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    # ── DELETE — clear config ──
    def do_DELETE(self):
        if not kv_available():
            self._respond(503, {"error": "kv_not_configured"}); return

        qs  = parse_qs(urlparse(self.path).query)
        pin = (qs.get("pin", [""])[0]).strip()

        if not pin:
            self._respond(400, {"error": "PIN مطلوب"}); return

        try:
            kv_delete(pin)
            self._respond(200, {"ok": True, "msg": "تم الحذف"})
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
