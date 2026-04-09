"""
TikSave Pro — Render.com server
All API module names are prefixed with tik_ to avoid Python stdlib conflicts.
"""
import os, sys, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

# Append so stdlib takes priority — avoids ANY name shadowing
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

import tik_profile   as profile_mod   # renamed: profile.py conflicts with stdlib
import download      as download_mod
import upload        as upload_mod
import dropbox_oauth as token_mod     # renamed: token.py conflicts with stdlib
import storage       as storage_mod
import test_keys     as test_keys_mod
import settings      as settings_mod

ROUTES = {
    "/api/profile":   profile_mod.handler,
    "/api/download":  download_mod.handler,
    "/api/upload":    upload_mod.handler,
    "/api/token":     token_mod.handler,
    "/api/storage":   storage_mod.handler,
    "/api/test_keys": test_keys_mod.handler,
    "/api/settings":  settings_mod.handler,
}

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), 'public')

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css':  'text/css',
    '.js':   'application/javascript',
    '.json': 'application/json',
    '.png':  'image/png',
    '.ico':  'image/x-icon',
    '.svg':  'image/svg+xml',
}

class MainHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _route_api(self):
        path = urlparse(self.path).path.rstrip('/')
        if path not in ROUTES:
            return False
        try:
            h = ROUTES[path].__new__(ROUTES[path])
            BaseHTTPRequestHandler.__init__(h, self.request, self.client_address, self.server)
            h.rfile   = self.rfile
            h.wfile   = self.wfile
            h.headers = self.headers
            h.path    = self.path
            h.command = self.command
            method = getattr(h, f'do_{self.command}', None)
            if method:
                method()
                return True
        except Exception as e:
            print(f"[ERROR] {path}: {e}", flush=True)
        return False

    def _serve_static(self, filepath):
        ext   = os.path.splitext(filepath)[1].lower()
        ctype = MIME.get(ext, 'application/octet-stream')
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def _handle_static(self):
        path = urlparse(self.path).path
        if path in ('/auth-callback', '/auth-callback.html'):
            self._serve_static(os.path.join(PUBLIC_DIR, 'auth-callback.html'))
        else:
            self._serve_static(os.path.join(PUBLIC_DIR, 'index.html'))

    def do_GET(self):
        if not self._route_api(): self._handle_static()

    def do_POST(self):
        if not self._route_api():
            self.send_response(404); self._cors(); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_DELETE(self):
        if not self._route_api():
            self.send_response(404); self.end_headers()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Each request in its own thread — no blocking."""
    daemon_threads = True


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 TikSave running on port {port}", flush=True)
    server = ThreadedHTTPServer(('0.0.0.0', port), MainHandler)
    server.serve_forever()
