"""
POST /api/upload
Body JSON: { video_url, filename, drop_folder, app_key, app_secret, refresh_token }

Features:
  - Refreshes Dropbox access token automatically
  - Checks if file already exists BEFORE downloading (duplicate prevention)
  - Downloads video server-side (bypasses browser CORS)
  - Uploads to Dropbox with overwrite=false when checking duplicates
"""
import json
import requests
from http.server import BaseHTTPRequestHandler


def get_access_token(app_key, app_secret, refresh_token):
    r = requests.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "client_id":     app_key,
            "client_secret": app_secret,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def file_exists_on_dropbox(path, access_token):
    """Returns True if the file already exists in Dropbox."""
    r = requests.post(
        "https://api.dropbox.com/2/files/get_metadata",
        headers={
            "Authorization":  f"Bearer {access_token}",
            "Content-Type":   "application/json",
        },
        json={"path": path},
        timeout=10,
    )
    if r.status_code == 200:
        return True
    if r.status_code == 409:
        # 409 = path not found → file does not exist
        return False
    r.raise_for_status()
    return False


def upload_to_dropbox(video_bytes, path, access_token):
    r = requests.post(
        "https://content.dropboxapi.com/2/files/upload",
        headers={
            "Authorization":   f"Bearer {access_token}",
            "Dropbox-API-Arg": json.dumps({
                "path":       path,
                "mode":       "overwrite",
                "autorename": False,
                "mute":       True,
            }),
            "Content-Type": "application/octet-stream",
        },
        data=video_bytes,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        video_url     = body.get("video_url",     "").strip()
        filename      = body.get("filename",      "video.mp4").strip()
        drop_folder   = body.get("drop_folder",   "/videos").strip()
        app_key       = body.get("app_key",       "").strip()
        app_secret    = body.get("app_secret",    "").strip()
        refresh_token = body.get("refresh_token", "").strip()

        if not video_url:
            self._respond(400, {"error": "video_url مطلوب"}); return
        if not all([app_key, app_secret, refresh_token]):
            self._respond(400, {"error": "Dropbox credentials ناقصة"}); return

        # Get fresh access token
        try:
            access_token = get_access_token(app_key, app_secret, refresh_token)
        except Exception as e:
            self._respond(401, {"error": f"Dropbox token refresh فشل: {e}"}); return

        dropbox_path = f"{drop_folder.rstrip('/')}/{filename}"

        # ── Duplicate check ──────────────────────────────
        try:
            if file_exists_on_dropbox(dropbox_path, access_token):
                self._respond(200, {
                    "ok":      True,
                    "skipped": True,
                    "path":    dropbox_path,
                    "reason":  "already_exists",
                })
                return
        except Exception:
            pass  # non-fatal — proceed with upload

        # ── Download video server-side (no CORS issues) ──
        try:
            vr = requests.get(
                video_url, timeout=60,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            vr.raise_for_status()
            video_bytes = vr.content
        except Exception as e:
            self._respond(502, {"error": f"تحميل الفيديو فشل: {e}"}); return

        # ── Upload to Dropbox ────────────────────────────
        try:
            result = upload_to_dropbox(video_bytes, dropbox_path, access_token)
            self._respond(200, {
                "ok":      True,
                "skipped": False,
                "path":    result.get("path_display", dropbox_path),
            })
        except requests.HTTPError as e:
            err_text = e.response.text[:300]
            # Detect storage full (507 or Dropbox storage error)
            if e.response.status_code == 507 or 'storage' in err_text.lower() or 'insufficient' in err_text.lower():
                self._respond(507, {"error": "storage_full: Dropbox امتلأت المساحة"})
            else:
                self._respond(e.response.status_code,
                              {"error": f"Dropbox upload فشل: {err_text}"})
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
