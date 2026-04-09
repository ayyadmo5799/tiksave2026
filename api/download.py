"""
GET /api/download?video_id=xxx&rapid_key=yyy
Tries multiple free API providers in order:
  1. tiktok-video-no-watermark2 (RapidAPI) 
  2. tiktok-scraper7 (RapidAPI - different quota)
  3. tiktok-download-without-watermark (RapidAPI - different quota)
Returns { url: "https://..." }
"""
import json
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


PROVIDERS = [
    {
        "name": "tiktok-video-no-watermark2",
        "url": "https://tiktok-video-no-watermark2.p.rapidapi.com/?url=https://www.tiktok.com/video/{video_id}&hd=1",
        "host": "tiktok-video-no-watermark2.p.rapidapi.com",
        "extract": lambda d: (d.get("data") or {}).get("play") or
                             (d.get("data") or {}).get("hdplay") or
                             (d.get("data") or {}).get("nwm_video_url_HQ") or
                             (d.get("data") or {}).get("nwm_video_url"),
    },
    {
        "name": "tiktok-scraper7",
        "url": "https://tiktok-scraper7.p.rapidapi.com/?url=https://www.tiktok.com/video/{video_id}&hd=1",
        "host": "tiktok-scraper7.p.rapidapi.com",
        "extract": lambda d: (d.get("data") or {}).get("play") or
                             (d.get("data") or {}).get("hdplay"),
    },
    {
        "name": "tiktok-download-without-watermark",
        "url": "https://tiktok-download-without-watermark.p.rapidapi.com/analysis?url=https://www.tiktok.com/video/{video_id}&hd=1",
        "host": "tiktok-download-without-watermark.p.rapidapi.com",
        "extract": lambda d: (d.get("data") or {}).get("play") or
                             (d.get("data") or {}).get("wmplay"),
    },
]


def try_provider(provider, video_id, rapid_key):
    url = provider["url"].format(video_id=video_id)
    headers = {
        "x-rapidapi-key":  rapid_key,
        "x-rapidapi-host": provider["host"],
    }
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code == 429:
        return None, 429
    r.raise_for_status()
    data = r.json()
    link = provider["extract"](data)
    return link, 200


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        def p(k, d=""): return (qs.get(k, [d])[0]).strip()

        video_id  = p("video_id")
        rapid_key = p("rapid_key")

        if not video_id or not rapid_key:
            self._respond(400, {"error": "video_id و rapid_key مطلوبان"})
            return

        # Try all providers
        for provider in PROVIDERS:
            try:
                link, status = try_provider(provider, video_id, rapid_key)
                if status == 429:
                    continue  # try next provider
                if link:
                    self._respond(200, {"url": link, "provider": provider["name"]})
                    return
            except Exception:
                continue  # try next provider

        self._respond(429, {"error": "all_quota_exceeded"})

    def _respond(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
