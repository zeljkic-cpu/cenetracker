import os, json, urllib.request, time, re
from datetime import datetime

API_KEY_FILE = "api_key.txt"

TRGOVINE = [
    {"store": "Lidl", "url": "https://moj-letak.si/lidl-katalogi"},
]

def get_api_key():
    if os.path.exists(API_KEY_FILE):
        k = open(API_KEY_FILE).read().strip()
        if k: return k
    return ""

def preberi_stran(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0",
        "Accept": "text/html,*/*",
        "Accept-Language": "sl-SI,sl;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "ignore")

def razcleni_izdelke(html, store):
    """Izvleče tabelo z izdelki in cenami iz moj-letak.si"""
    rezultati = []
    
    # Poišči vrstice tabele z izdelki
    # Format: | katalog | stran | izdelek | opis | cena |
    pattern = r'<td[^>]*>.*?<\/td>\s*<td[^>]*>.*?<\/td>\s*<td[^>]*>.*?<\/td>\s*<td[^>]*>(.*?)<\/td>\s*<td[^>]*>([\d,\.]+)\s*€<\/td>'
    
    # Enostavnejši pristop - poišči vse cene z opisi
    # Iščemo vzorec: naziv | cena €
    rows = re.findall(r'<td[^>]*>\s*([^<]{3,80})\s*</td>\s*<td[^>]*>\s*([\d]+[,\.][\d]+)\s*€\s*</td>', html)
    
    for naziv, cena_str in rows:
        naziv = re.sub(r'\s+', ' ', naziv).strip()
        naziv = re.sub(r'<[^>]+>', '', naziv).strip()
        if len(naziv) < 3: continue
        try:
            cena = float(cena_str.replace(',', '.'))
            rezultati.append({"store": store, "product": naziv, "price": cena})
        except:
            continue
    
    return rezultati

def normaliziraj(s):
    """Odstrani presledke, pomišljaje, naredi male črke."""
    import re
    s = s.lower()
    s = re.sub(r'[-_]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def ujemi_artikel(naziv, items):
    """Poišče kateri artikel iz seznama ustreza nazivu v letaku."""
    naziv_n = normaliziraj(naziv)
    for item in items:
        item_n = normaliziraj(item["name"])
        # Vse ključne besede artikla morajo biti v nazivu
        kljucne = [k for k in item_n.split() if len(k) > 2]
        if kljucne and all(k in naziv_n for k in kljucne):
            return item
        # Ali obratno
        if item_n in naziv_n:
            return item
    return None

def poisci_cene(items_data, api_key):
    items = items_data
    vse_cene = {str(i["id"]): [] for i in items}

    print(f"\n🔍 Iščem v letakih: {', '.join(i['name'] for i in items)}\n")

    for t in TRGOVINE:
        store = t["store"]
        print(f"📄 {store}...", end=" ", flush=True)
        try:
            html = preberi_stran(t["url"])
            vsi = razcleni_izdelke(html, store)
            
            najdeno = 0
            if vsi: print(f"    Vzorec izdelkov: {[v['product'] for v in vsi[:8]]}")
            for item in items:
                ujemanja = []
                for izdelek in vsi:
                    if ujemi_artikel(izdelek["product"], [item]):
                        ujemanja.append(izdelek)
                
                for u in ujemanja:
                    # Določi enoto iz naziva
                    naziv = u["product"].lower()
                    cena = u["price"]
                    
                    # Izvleči količino
                    kol_match = re.search(r'(\d+[,\.]?\d*)\s*(l|ml|kg|g|kos|kom)', naziv)
                    if kol_match:
                        kol = float(kol_match.group(1).replace(',','.'))
                        enota = kol_match.group(2)
                        if enota == "ml": cpu = cena/(kol/1000); ut = "l"
                        elif enota == "l": cpu = cena/kol; ut = "l"
                        elif enota == "g": cpu = cena/(kol/1000); ut = "kg"
                        elif enota == "kg": cpu = cena/kol; ut = "kg"
                        else: cpu = cena; ut = "kos"
                        unit_str = f"{kol} {enota}"
                    else:
                        cpu = cena; ut = "kos"; unit_str = "1 kos"
                    
                    vse_cene[str(item["id"])].append({
                        "store": store,
                        "product": u["product"],
                        "price": round(cena, 2),
                        "unit": unit_str,
                        "pricePerUnit": round(cpu, 2),
                        "unitType": ut
                    })
                    najdeno += 1
            
            print(f"→ {len(vsi)} izdelkov, {najdeno} ujemanj ✓")
        except Exception as e:
            print(f"→ napaka: {e}")
        time.sleep(0.5)

    # Sestavi top 3 po ceni na enoto
    rezultati = {}
    for item in items:
        k = str(item["id"])
        cene = sorted(vse_cene.get(k, []), key=lambda x: x["pricePerUnit"])[:3]
        rezultati[k] = {
            "top3": cene,
            "at": datetime.now().strftime("%d.%m.%Y %H:%M")
        }

    with open("ct_prices.json", "w", encoding="utf-8") as f:
        json.dump(rezultati, f, ensure_ascii=False)

    print(f"\n✅ Shranjeno v ct_prices.json")
    najdenih = sum(1 for v in rezultati.values() if v["top3"])
    print(f"   Cene najdene za {najdenih}/{len(items)} izdelkov")
    return rezultati

if __name__ == "__main__":
    api_key = get_api_key()
    if os.path.exists("ct_items.json"):
        items = json.load(open("ct_items.json", encoding="utf-8"))
    else:
        print("❌ Ni ct_items.json")
        exit(1)
    poisci_cene(items, api_key)
    input("\nPritisni Enter za izhod...")
