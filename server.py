import http.server, urllib.request, urllib.error, json, os, base64, time, threading
from datetime import datetime

PORT = 7777
API_KEY_FILE = "api_key.txt"

LETAKI = [
    {"store":"Lidl",     "url":"https://www.lidl.si/spletni-katalog"},
    {"store":"Hofer",    "url":"https://www.hofer.si/sl/letak.html"},
    {"store":"Mercator", "url":"https://www.mercator.si/letaki/"},
    {"store":"Spar",     "url":"https://www.spar.si/ponudba/letaki"},
    {"store":"Tus",      "url":"https://www.tus.si/letaki/"},
    {"store":"Eurospin", "url":"https://www.eurospin.si/letaki"},
]

iskanje_status = {"running": False, "msg": "Pripravljen", "done": 0, "total": 0}

def get_api_key():
    if os.path.exists(API_KEY_FILE):
        k = open(API_KEY_FILE).read().strip()
        if k: return k
    return ""

def save_api_key(k):
    open(API_KEY_FILE,"w").write(k)

def claude_pdf(api_key, pdf_b64, prompt):
    body = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": 1500,
        "messages": [{"role":"user","content":[
            {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":pdf_b64}},
            {"type":"text","text":prompt}
        ]}]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["content"][0]["text"]

def prenesi_pdf(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ct = r.headers.get("Content-Type","")
            data = r.read()
        return data if "pdf" in ct.lower() or url.lower().endswith(".pdf") else None
    except:
        return None

def poisci_cene_v_ozadju(items, api_key):
    global iskanje_status
    iskanje_status = {"running":True,"msg":"Zaganjam brskalnik...","done":0,"total":len(LETAKI)}
    
    # Shrani items za skripto
    with open("ct_items.json","w",encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import beri_letake

        def status_cb(store, done):
            iskanje_status["msg"] = f"Prebiram {store}..."
            iskanje_status["done"] = done

        # Zagotovi pravilen format items
        items_ok = []
        for it in items:
            if isinstance(it, dict) and "name" in it:
                items_ok.append({"id": it.get("id", it["name"]), "name": it["name"]})
        rezultati = beri_letake.poisci_cene(items_ok, api_key)
        iskanje_status = {"running":False,"msg":"Končano!","done":len(LETAKI),"total":len(LETAKI)}
        print("✅ Iskanje zaključeno")
    except Exception as e:
        iskanje_status = {"running":False,"msg":f"Napaka: {e}","done":0,"total":len(LETAKI)}
        print(f"❌ Napaka: {e}")

class Handler(http.server.SimpleHTTPRequestHandler):
    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type,x-api-key,anthropic-version')

    def do_OPTIONS(self):
        self.send_response(200)
        self.cors()
        self.end_headers()

    def do_GET(self):
        # Status iskanja
        if self.path == '/status':
            self.send_response(200)
            self.cors()
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps(iskanje_status).encode())
            return
        # Vrni shranjene cene
        if self.path == '/prices':
            self.send_response(200)
            self.cors()
            self.send_header('Content-Type','application/json')
            self.end_headers()
            if os.path.exists("ct_prices.json"):
                self.wfile.write(open("ct_prices.json","rb").read())
            else:
                self.wfile.write(b'{}')
            return
        if self.path == '/update':
            import subprocess
            try:
                result = subprocess.run(['git', 'pull', 'origin', 'main'],
                    capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
                output = result.stdout + result.stderr
                self.send_response(200)
                self.cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "msg": output}).encode())
                print(f"Posodobitev: {output.strip()}")
            except Exception as e:
                self.send_response(500)
                self.cors()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "msg": str(e)}).encode())
            return
        super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length',0))
        body = self.rfile.read(length)

        # Proxy do Anthropic API
        if self.path == '/api/anthropic':
            api_key = self.headers.get('x-api-key','')
            if not api_key: api_key = get_api_key()
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages', data=body,
                headers={'Content-Type':'application/json','x-api-key':api_key,'anthropic-version':'2023-06-01'}
            )
            try:
                with urllib.request.urlopen(req) as r:
                    result = r.read()
                self.send_response(200)
            except urllib.error.HTTPError as e:
                result = e.read()
                self.send_response(e.code)
            self.cors()
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(result)
            return

        # Shrani API ključ
        if self.path == '/save-key':
            data = json.loads(body)
            save_api_key(data.get('key',''))
            self.send_response(200)
            self.cors()
            self.end_headers()
            self.wfile.write(b'OK')
            return

        # Začni iskanje cen v ozadju
        if self.path == '/search':
            global iskanje_status
            if iskanje_status["running"]:
                self.send_response(200)
                self.cors()
                self.end_headers()
                self.wfile.write(b'{"status":"running"}')
                return
            data = json.loads(body)
            items = data.get('items',[])
            api_key = data.get('apiKey','') or get_api_key()
            if api_key: save_api_key(api_key)
            t = threading.Thread(target=poisci_cene_v_ozadju, args=(items, api_key), daemon=True)
            t.start()
            self.send_response(200)
            self.cors()
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"started"}')
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"\n  CeneTracker strežnik zagnan!")
print(f"  Odpri: http://localhost:{PORT}/app.html")
print(f"\n  Za zaustavitev pritisni Ctrl+C\n")

with http.server.HTTPServer(('',PORT),Handler) as httpd:
    httpd.serve_forever()
