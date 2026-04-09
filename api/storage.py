"""
GET /api/storage
Params: app_key, app_secret, refresh_token, folder
Returns Dropbox space usage + file count in folder
"""
import json, requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


def get_token(app_key, app_secret, refresh):
    r = requests.post("https://api.dropbox.com/oauth2/token",
        data={"grant_type":"refresh_token","refresh_token":refresh,
              "client_id":app_key,"client_secret":app_secret},
        timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def get_space(token):
    r = requests.post("https://api.dropbox.com/2/users/get_space_usage",
        headers={"Authorization":f"Bearer {token}"},timeout=10)
    r.raise_for_status()
    d = r.json()
    used  = d.get("used", 0)
    alloc = d.get("allocation", {}).get("allocated", 0)
    return used, alloc


def get_folder_info(token, folder):
    """List folder and count files + total size"""
    files = []
    cursor = None
    has_more = True

    while has_more:
        if cursor:
            r = requests.post(
                "https://api.dropbox.com/2/files/list_folder/continue",
                headers={"Authorization":f"Bearer {token}",
                         "Content-Type":"application/json"},
                json={"cursor": cursor}, timeout=15)
        else:
            r = requests.post(
                "https://api.dropbox.com/2/files/list_folder",
                headers={"Authorization":f"Bearer {token}",
                         "Content-Type":"application/json"},
                json={"path": folder, "recursive": False,
                      "limit": 2000}, timeout=15)

        if r.status_code == 409:
            # folder doesn't exist yet
            return 0, 0

        r.raise_for_status()
        data     = r.json()
        entries  = data.get("entries", [])
        has_more = data.get("has_more", False)
        cursor   = data.get("cursor")

        for e in entries:
            if e.get(".tag") == "file":
                files.append(e.get("size", 0))

    count      = len(files)
    total_size = sum(files)
    return count, total_size


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        def p(k): return (qs.get(k, [""])[0]).strip()

        app_key = p("app_key")
        app_sec = p("app_secret")
        refresh = p("refresh_token")
        folder  = p("folder") or "/videos"

        if not all([app_key, app_sec, refresh]):
            self._respond(400, {"error": "credentials ناقصة"})
            return

        try:
            token = get_token(app_key, app_sec, refresh)
            used, alloc = get_space(token)
            count, folder_size = get_folder_info(token, folder)

            self._respond(200, {
                "used":        used,
                "allocated":   alloc,
                "free":        max(0, alloc - used),
                "pct":         round(used / alloc * 100, 1) if alloc else 0,
                "folder":      folder,
                "file_count":  count,
                "folder_size": folder_size,
            })

        except requests.HTTPError as e:
            self._respond(e.response.status_code,
                {"error": f"Dropbox: {e.response.text[:200]}"})
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
