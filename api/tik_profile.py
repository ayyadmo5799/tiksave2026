"""
GET /api/profile
Params: username, rapid_key, apify_token, scraper_api_key, max_dur, cursor, source

Priority order:
  1. RapidAPI (3 providers, rotate keys)        → 1500 req/month free
  2. Apify TikTok Scraper                       → $5 credit/month free (~1000 videos)
  3. ScraperAPI + TikTok web scraping           → 1000 req/month free
"""
import json, requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ═══════════════════════════════════════════════
#  1. RAPIDAPI
# ═══════════════════════════════════════════════
def fetch_rapid_page(username, rapid_key, cursor):
    r = requests.get(
        "https://tiktok-video-no-watermark2.p.rapidapi.com/user/posts",
        params={"unique_id": username, "count": 20, "cursor": cursor},
        headers={
            "x-rapidapi-key":  rapid_key,
            "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

def parse_rapid(data, max_dur):
    raw   = data.get("data") or {}
    # Try multiple known response structures
    items = (raw.get("videos") or raw.get("aweme_list") or
             raw.get("itemList") or raw.get("items") or
             data.get("videos") or data.get("aweme_list") or [])
    print(f"[DEBUG parse_rapid] data keys={list(data.keys())}, raw keys={list(raw.keys()) if isinstance(raw,dict) else '?'}, items count={len(items)}", flush=True)
    videos = []
    for v in items:
        dur = _dur(v.get("duration") or v.get("video", {}).get("duration", 0))
        if dur <= 0 or dur > max_dur: continue
        vid_id   = str(v.get("video_id") or v.get("aweme_id") or v.get("id") or "")
        title    = (v.get("title") or v.get("desc") or vid_id)[:80]
        play_url = (v.get("play") or v.get("hdplay") or
                    v.get("nwm_video_url_HQ") or v.get("nwm_video_url") or
                    v.get("wmplay") or "")
        videos.append({"id": vid_id, "duration": dur, "title": title, "play_url": play_url})
    has_more = bool(raw.get("hasMore") or raw.get("has_more") or False)
    return videos, has_more, raw.get("cursor") or 0


# ═══════════════════════════════════════════════
#  2. APIFY
# ═══════════════════════════════════════════════
def fetch_apify_all(username, token, max_dur):
    r = requests.post(
        "https://api.apify.com/v2/acts/clockworks~tiktok-profile-scraper/run-sync-get-dataset-items",
        params={"token": token, "timeout": 120},
        json={
            "profiles": [f"https://www.tiktok.com/@{username}"],
            "resultsPerPage": 200,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        },
        timeout=130,
    )
    r.raise_for_status()
    videos = []
    for item in r.json():
        dur = _dur(item.get("videoMeta", {}).get("duration") or item.get("duration") or 0)
        if dur <= 0 or dur > max_dur: continue
        vid_id   = str(item.get("id") or item.get("videoId") or "")
        title    = (item.get("text") or item.get("desc") or vid_id)[:80]
        play_url = (item.get("videoUrlNoWatermark") or
                    item.get("videoUrl") or
                    item.get("downloadAddr") or
                    item.get("video_url") or
                    (item.get("mediaUrls") or [""])[0] or "")
        play_url = str(play_url or "")
        if not play_url:
            print(f"[APIFY DEBUG] no URL, keys={list(item.keys())[:15]}", flush=True)
        videos.append({"id": vid_id, "duration": dur, "title": title, "play_url": play_url})
    return videos


# ═══════════════════════════════════════════════
#  3. SCRAPERAPI  (proxied TikTok web scrape)
# ═══════════════════════════════════════════════
def fetch_scraper_page(username, api_key, cursor):
    """
    ScraperAPI proxies a request to TikTok's internal API.
    Uses their structured data endpoint for TikTok.
    """
    tiktok_url = (
        f"https://www.tiktok.com/api/post/item_list/"
        f"?aid=1988&count=20&cursor={cursor}&secUid=&uniqueId={username}"
    )
    r = requests.get(
        "https://api.scraperapi.com/",
        params={
            "api_key": api_key,
            "url": tiktok_url,
            "render": "false",
            "country_code": "us",
        },
        timeout=30,
    )
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        raise ValueError(f"ScraperAPI bad response: {r.text[:200]}")

    items    = data.get("itemList") or []
    has_more = bool(data.get("hasMore"))
    next_cur = data.get("cursor") or (cursor + 20)
    videos   = []
    for v in items:
        vm  = v.get("video") or {}
        dur = _dur(vm.get("duration") or v.get("duration") or 0)
        if dur <= 0 or dur > max_dur: continue
        vid_id   = str(v.get("id") or "")
        title    = (v.get("desc") or vid_id)[:80]
        play_url = vm.get("playAddr") or vm.get("downloadAddr") or ""
        videos.append({"id": vid_id, "duration": dur, "title": title, "play_url": play_url})
    return videos, has_more, next_cur


# ═══════════════════════════════════════════════
#  4. BRIGHT DATA
# ═══════════════════════════════════════════════
def fetch_brightdata_page(username, token, cursor):
    """
    Bright Data — uses their Scraping Browser / Web Unlocker API.
    Correct endpoint: https://api.brightdata.com/request (zone-based)
    Token = API token from brightdata.com dashboard.
    """
    tiktok_url = (
        f"https://www.tiktok.com/api/post/item_list/"
        f"?aid=1988&count=20&cursor={cursor}&uniqueId={username}"
    )
    # Try zone-based proxy request
    r = requests.get(
        tiktok_url,
        proxies={
            "http":  f"http://brd-customer-hl_00000000-zone-web_unlocker1:{token}@brd.superproxy.io:22225",
            "https": f"http://brd-customer-hl_00000000-zone-web_unlocker1:{token}@brd.superproxy.io:22225",
        },
        verify=False,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        raise ValueError(f"Bright Data bad JSON: {r.text[:200]}")

    items    = data.get("itemList") or []
    has_more = bool(data.get("hasMore"))
    next_cur = data.get("cursor") or (cursor + 20)
    return items, has_more, next_cur


# ═══════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════
def _dur(v):
    try: return float(v)
    except: return 0


# ═══════════════════════════════════════════════
#  HANDLER
# ═══════════════════════════════════════════════
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
        def p(k, d=""): return (qs.get(k, [d])[0]).strip()

        username       = p("username")
        rapid_key      = p("rapid_key")
        apify_token    = p("apify_token")
        scraper_key    = p("scraper_key")
        max_dur        = int(p("max_dur", "120"))
        cursor         = int(p("cursor",  "0"))
        source         = p("source", "rapid")

        if not username:
            self._respond(400, {"error": "username مطلوب"}); return

        # ── Source: Apify ──
        if source == "apify":
            if not apify_token:
                self._respond(400, {"error": "apify_token مطلوب"}); return
            try:
                videos = fetch_apify_all(username, apify_token, max_dur)
                self._respond(200, {"videos": videos, "has_more": False,
                                    "cursor": 0, "source": "apify", "total": len(videos)})
            except requests.HTTPError as e:
                self._respond(e.response.status_code, {"error": f"Apify: {e.response.text[:300]}"})
            except Exception as e:
                self._respond(500, {"error": str(e)})
            return

        # ── Source: ScraperAPI ──
        if source == "scraper":
            if not scraper_key:
                self._respond(400, {"error": "scraper_key مطلوب"}); return
            try:
                videos, has_more, next_cur = fetch_scraper_page(username, scraper_key, cursor)
                self._respond(200, {"videos": videos, "has_more": has_more,
                                    "cursor": next_cur, "source": "scraper"})
            except requests.HTTPError as e:
                self._respond(e.response.status_code, {"error": f"ScraperAPI: {e.response.text[:300]}"})
            except Exception as e:
                self._respond(500, {"error": str(e)})
            return

        # ── Source: Bright Data ──
        if source == "brightdata":
            bdtoken = p("bd_token")
            if not bdtoken:
                self._respond(400, {"error": "bd_token مطلوب"}); return
            try:
                cursor_val = int(p("cursor","0"))
                items, has_more, next_cur = fetch_brightdata_page(username, bdtoken, cursor_val)
                videos = []
                for v in items:
                    vm  = v.get("video") or {}
                    dur = _dur(vm.get("duration") or v.get("duration") or 0)
                    if dur <= 0 or dur > max_dur: continue
                    vid_id   = str(v.get("id") or "")
                    title    = (v.get("desc") or vid_id)[:80]
                    play_url = vm.get("playAddr") or vm.get("downloadAddr") or ""
                    videos.append({"id": vid_id, "duration": dur, "title": title, "play_url": play_url})
                self._respond(200, {"videos": videos, "has_more": has_more,
                                    "cursor": next_cur, "source": "brightdata"})
            except requests.HTTPError as e:
                self._respond(e.response.status_code, {"error": f"BrightData: {e.response.text[:200]}"})
            except Exception as e:
                self._respond(500, {"error": str(e)})
            return

        # ── Source: RapidAPI (default) ──
        if not rapid_key:
            self._respond(400, {"error": "rapid_key مطلوب"}); return
        try:
            data = fetch_rapid_page(username, rapid_key, cursor)
            videos, has_more, next_cur = parse_rapid(data, max_dur)
            self._respond(200, {"videos": videos, "has_more": has_more,
                                "cursor": next_cur, "source": "rapid"})
        except requests.HTTPError as e:
            self._respond(e.response.status_code, {"error": f"RapidAPI: {e.response.text[:300]}"})
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
