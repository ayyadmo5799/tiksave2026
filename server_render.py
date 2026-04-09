"""
TikSave Pro — Render.com server — FIXED routing
"""
import os, sys, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api')
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

import tik_profile   as profile_mod
import download      as download_mod
import upload        as upload_mod
import dropbox_oauth as token_mod
import storage       as storage_mod
import test_keys     as test_keys_mod
import settings      as settings_mod
import ping          as ping_mod

ROUTES = {
    "/api/profile":   profile_mod.handler,
    "/api/download":  download_mod.handler,
    "/api/upload":    upload_mod.handler,
    "/api/token":     token_mod.handler,
    "/api/storage":   storage_mod.handler,
    "/api/test_keys": test_keys_mod.handler,
    "/api/settings":  settings_mod.handler,
    "/api/ping":      ping_mod.handler,
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
            HandlerClass = ROUTES[path]
            # Use object.__new__ to skip __init__ (which would re-read the socket)
            h = object.__new__(HandlerClass)
            # Copy ALL attributes the BaseHTTPRequestHandler methods need
            h.rfile            = self.rfile
            h.wfile            = self.wfile
            h.headers          = self.headers
            h.path             = self.path
            h.command          = self.command
            h.server           = self.server
            h.request          = self.request
            h.client_address   = self.client_address
            h.requestline      = self.requestline
            h.request_version  = self.request_version
            h.close_connection = self.close_connection
            h.raw_requestline  = getattr(self, 'raw_requestline', b'')
            method = getattr(h, f'do_{self.command}', None)
            if method:
                method()
                return True
        except Exception as e:
            print(f"[ERROR] {path}: {e}", flush=True)
            import traceback; traceback.print_exc()
        return False

    def _serve_static(self, filepath):
        ext   = os.path.splitext(filepath)[1].lower()
        ctype = MIME.get(ext, 'application/octet-stream')
        try:
            with open(filepath, 'rb') as f: data = f.read()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404); self.end_headers(); self.wfile.write(b'Not Found')

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
    daemon_threads = True


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 TikSave running on port {port}", flush=True)
    ThreadedHTTPServer(('0.0.0.0', port), MainHandler).serve_forever()
