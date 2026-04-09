"""
POST /api/test_keys
Tests: RapidAPI keys[], Apify tokens[], ScraperAPI keys[], Dropbox, Bright Data
"""
import json, requests, time
from http.server import BaseHTTPRequestHandler


def test_rapid(key):
    start=time.time()
    try:
        r=requests.get(
            "https://tiktok-video-no-watermark2.p.rapidapi.com/user/posts",
            params={"unique_id":"tiktok","count":1,"cursor":0},
            headers={"x-rapidapi-key":key,"x-rapidapi-host":"tiktok-video-no-watermark2.p.rapidapi.com"},
            timeout=10)
        ms=int((time.time()-start)*1000)
        if r.status_code==200: return {"ok":True, "status":"✅ شغال","ms":ms}
        if r.status_code==429: return {"ok":False,"status":"❌ quota خلص (429)","ms":ms}
        if r.status_code==403: return {"ok":False,"status":"❌ مفتاح غير صالح (403)","ms":ms}
        return {"ok":False,"status":f"⚠️ كود {r.status_code}","ms":ms}
    except requests.Timeout:
        return {"ok":False,"status":"⚠️ timeout (10s)","ms":10000}
    except Exception as e:
        return {"ok":False,"status":f"❌ {str(e)[:50]}","ms":0}


def test_apify(token):
    start=time.time()
    try:
        r=requests.get("https://api.apify.com/v2/users/me",
            params={"token":token},timeout=10)
        ms=int((time.time()-start)*1000)
        if r.status_code==200:
            d=r.json().get("data",{})
            username=d.get("username","")
            plan=d.get("plan",{})
            credit=plan.get("monthlyUsageCreditsUsd",5)
            used_cu=d.get("monthlyUsage",{}).get("actorComputeUnits",0)
            used_usd=round(used_cu*0.004,2)
            remaining=round(max(0,credit-used_usd),2)
            return {"ok":True,"status":"✅ شغال","ms":ms,
                    "detail":f"@{username} | رصيد متبقي ~${remaining}/{credit}"}
        if r.status_code==401:
            return {"ok":False,"status":"❌ token غير صالح (401)","ms":ms}
        return {"ok":False,"status":f"⚠️ {r.status_code}","ms":ms}
    except Exception as e:
        return {"ok":False,"status":f"❌ {str(e)[:50]}","ms":0}


def test_scraper(key):
    start=time.time()
    try:
        r=requests.get("https://api.scraperapi.com/account",
            params={"api_key":key},timeout=10)
        ms=int((time.time()-start)*1000)
        if r.status_code==200:
            d=r.json()
            used=d.get("requestCount",0)
            limit=d.get("requestLimit",1000)
            remaining=max(0,limit-used)
            ok=remaining>0
            return {"ok":ok,
                    "status":"✅ شغال" if ok else "❌ quota خلص",
                    "ms":ms,
                    "detail":f"مستخدم {used}/{limit} | متبقي {remaining}"}
        if r.status_code==403:
            return {"ok":False,"status":"❌ مفتاح غير صالح (403)","ms":ms}
        return {"ok":False,"status":f"⚠️ {r.status_code}","ms":ms}
    except Exception as e:
        return {"ok":False,"status":f"❌ {str(e)[:50]}","ms":0}


def test_brightdata(token):
    start=time.time()
    try:
        r=requests.get("https://api.brightdata.com/user",
            headers={"Authorization":f"Bearer {token}"},timeout=10)
        ms=int((time.time()-start)*1000)
        if r.status_code==200:
            d=r.json()
            email=d.get("email","")
            balance=d.get("balance",0)
            return {"ok":True,"status":"✅ شغال","ms":ms,
                    "detail":f"{email} | رصيد: ${balance}"}
        if r.status_code==401:
            return {"ok":False,"status":"❌ token غير صالح (401)","ms":ms}
        return {"ok":False,"status":f"⚠️ {r.status_code}","ms":ms}
    except Exception as e:
        return {"ok":False,"status":f"❌ {str(e)[:50]}","ms":0}


def test_dropbox(app_key, app_secret, refresh):
    start=time.time()
    try:
        r=requests.post("https://api.dropbox.com/oauth2/token",
            data={"grant_type":"refresh_token","refresh_token":refresh,
                  "client_id":app_key,"client_secret":app_secret},
            timeout=10)
        ms1=int((time.time()-start)*1000)
        if r.status_code!=200:
            try:
                err=r.json().get("error_description","credentials غلط")
            except Exception:
                err=f"HTTP {r.status_code}"
            return {"ok":False,"status":f"❌ {err}","ms":ms1}

        token=r.json().get("access_token","")
        r2=requests.post("https://api.dropbox.com/2/users/get_current_account",
            headers={"Authorization":f"Bearer {token}"},timeout=10)
        ms2=int((time.time()-start)*1000)
        if r2.status_code!=200:
            return {"ok":False,"status":f"❌ account error {r2.status_code}","ms":ms2}

        acc=r2.json()
        name=acc.get("name",{}).get("display_name","")
        email=acc.get("email","")
        r3=requests.post("https://api.dropbox.com/2/users/get_space_usage",
            headers={"Authorization":f"Bearer {token}"},timeout=10)
        detail=f"{name} ({email})"
        if r3.status_code==200:
            sp=r3.json()
            used=sp.get("used",0)/1e9
            allc=sp.get("allocation",{}).get("allocated",0)/1e9
            pct=int(used/allc*100) if allc else 0
            detail+=f" | مساحة: {used:.1f}/{allc:.0f}GB ({pct}%)"
        return {"ok":True,"status":"✅ متصل","ms":ms2,"detail":detail}
    except Exception as e:
        return {"ok":False,"status":f"❌ {str(e)[:60]}","ms":0}


class handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()
    def do_POST(self):
        try:
            length=int(self.headers.get("Content-Length",0))
            body=json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body={}

        results={"rapid":[],"apify":[],"scraper":[],"brightdata":[],"dropbox":None}

        for k in (body.get("rapid_keys") or []):
            if k and k.strip():
                res=test_rapid(k.strip())
                res["key_preview"]=k.strip()[:16]+"…"
                results["rapid"].append(res)

        for t in (body.get("apify_tokens") or []):
            if t and t.strip():
                res=test_apify(t.strip())
                res["token_preview"]=t.strip()[:16]+"…"
                results["apify"].append(res)

        for k in (body.get("scraper_keys") or []):
            if k and k.strip():
                res=test_scraper(k.strip())
                res["key_preview"]=k.strip()[:16]+"…"
                results["scraper"].append(res)

        for t in (body.get("brightdata_tokens") or []):
            if t and t.strip():
                res=test_brightdata(t.strip())
                res["token_preview"]=t.strip()[:16]+"…"
                results["brightdata"].append(res)

        # Support both old single-account and new multi-account format
        drop_accounts = body.get("drop_accounts") or []
        if not drop_accounts:
            # legacy single-account fallback
            ak  = (body.get("drop_app_key","") or "").strip()
            asc = (body.get("drop_app_secret","") or "").strip()
            rf  = (body.get("drop_refresh","") or "").strip()
            if ak and asc and rf:
                drop_accounts = [{"key":ak,"secret":asc,"refresh":rf}]

        results["dropbox"] = []
        for idx, acc in enumerate(drop_accounts):
            ak  = (acc.get("key","") or "").strip()
            asc = (acc.get("secret","") or "").strip()
            rf  = (acc.get("refresh","") or "").strip()
            if ak and asc and rf:
                res = test_dropbox(ak, asc, rf)
                res["account"] = idx + 1
                res["key_preview"] = ak[:8]+"…"
                results["dropbox"].append(res)
            else:
                results["dropbox"].append({"ok":False,"status":"❌ بيانات ناقصة","ms":0,"account":idx+1})

        raw=json.dumps(results,ensure_ascii=False).encode()
        self.send_response(200); self._cors()
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
