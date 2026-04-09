"""
TikSave Pro — Unified server for Render.com
- ThreadingHTTPServer: handles multiple requests simultaneously (no blocking)
- Routes /api/* to Python handlers
- Serves public/ static files
"""
import os, sys, json, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

# ── Import API handlers ────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
import profile   as profile_mod
import download  as download_mod
import upload    as upload_mod
import token     as token_mod
import storage   as storage_mod
import test_keys as test_keys_mod
import settings  as settings_mod

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
    '.jpg':  'image/jpeg',
    '.svg':  'image/svg+xml',
    '.ico':  'image/x-icon',
}

class MainHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default logs

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _route_api(self):
        """Route to appropriate API handler. Returns True if handled."""
        path = urlparse(self.path).path.rstrip('/')
        if path not in ROUTES:
            return False

        # Create handler instance and manually wire it
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
        return False

    def _serve_static(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()
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
        if path == '/auth-callback' or path == '/auth-callback.html':
            self._serve_static(os.path.join(PUBLIC_DIR, 'auth-callback.html'))
        else:
            self._serve_static(os.path.join(PUBLIC_DIR, 'index.html'))

    def do_GET(self):
        if not self._route_api():
            self._handle_static()

    def do_POST(self):
        if not self._route_api():
            self.send_response(404); self._cors(); self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight
        path = urlparse(self.path).path.rstrip('/')
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_DELETE(self):
        if not self._route_api():
            self.send_response(404); self.end_headers()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in a separate thread — no blocking."""
    daemon_threads = True


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    server = ThreadedHTTPServer(('0.0.0.0', port), MainHandler)
    print(f"🚀 TikSave running on port {port} (threaded)")
    server.serve_forever()
