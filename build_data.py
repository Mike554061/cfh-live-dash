#!/usr/bin/env python3
"""
Build data.json for the 3PL Live Dashboard from a Routific export.

PIPELINE (hybrid, per the agreed architecture):
  1. Read the Routific data export (CSV or published Google-Sheet CSV URL).
     This carries the LIVE layer: lat/lng, Delivery status, arrival times, and the
     `Photos` column (Firebase proof-of-delivery image URLs).
  2. (optional) Enrich planned ETAs / stop order via the Routific VRP API using your
     API key  ->  POST https://api.routific.com/v1/vrp.
  3. (offline OCR bake) For each POD photo, OCR the bill of lading once and write
     items / quantities / signature into data.json, so the dashboard hover is instant.
  4. Emit data.json in the schema the dashboard consumes (see make_sample.py).

USAGE:
  export ROUTIFIC_API_KEY=...          # only needed for VRP enrichment (optional)
  python3 build_data.py routes_raw.csv
  python3 build_data.py "https://docs.google.com/.../pub?gid=0&single=true&output=csv"

DEPENDENCIES (all optional / degrade gracefully):
  pip install requests pillow pytesseract   # + `brew install tesseract` for OCR
"""
import csv, io, json, os, re, sys, datetime, urllib.request

API_KEY = os.environ.get("ROUTIFIC_API_KEY", "")
VRP_URL = "https://api.routific.com/v1/vrp"

# ---- column aliases (matches route-viz/build_data.py export schema) ----
def col(row, *names):
    for n in names:
        for k in row:
            if k and k.strip().lower() == n.lower():
                v = row[k]
                return v.strip() if isinstance(v, str) else v
    return ""

def fnum(v):
    try: return float(str(v).replace("$", "").replace(",", "").strip())
    except: return None

def fetch_csv(path):
    if path.startswith("http"):
        with urllib.request.urlopen(path) as r:
            return r.read().decode("utf-8", "replace")
    with open(path, encoding="utf-8-sig") as f:
        return f.read()

# ---- offline OCR of a proof-of-delivery / bill-of-lading photo ----
_OCR_READY = None
def ocr_ready():
    global _OCR_READY
    if _OCR_READY is None:
        try:
            import pytesseract, PIL  # noqa
            _OCR_READY = True
        except Exception:
            _OCR_READY = False
            sys.stderr.write("[ocr] pytesseract/Pillow not installed — POD photos kept, OCR skipped.\n")
    return _OCR_READY

ITEM_RE = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.{3,60}?)\s*$")
def ocr_pod(url):
    """Download a Firebase POD image and extract bill-of-lading line items."""
    if not url or not ocr_ready():
        return {"photo": url, "items": [], "ocrConfidence": None, "ocrRaw": "", "signature": None, "notes": ""} if url else None
    try:
        import pytesseract
        from PIL import Image
        with urllib.request.urlopen(url) as r:
            img = Image.open(io.BytesIO(r.read()))
        raw = pytesseract.image_to_string(img)
        items = []
        for ln in raw.splitlines():
            m = ITEM_RE.match(ln)
            if m:
                items.append({"item": m.group(2).strip(), "qty": int(m.group(1))})
        signed = bool(re.search(r"sign|signature|signed by", raw, re.I))
        return {"photo": url, "items": items, "ocrConfidence": 0.9 if items else 0.4,
                "ocrRaw": raw.strip(), "signature": signed, "notes": ""}
    except Exception as e:
        sys.stderr.write(f"[ocr] failed for {url[:60]}…: {e}\n")
        return {"photo": url, "items": [], "ocrConfidence": None, "ocrRaw": "", "signature": None, "notes": ""}

# ---- map a Routific delivery-status string to our 4-state model ----
def map_status(s):
    s = (s or "").lower()
    if "deliver" in s or "complete" in s or "done" in s: return "completed"
    if "fail" in s or "miss" in s or "skip" in s: return "missed"
    if "progress" in s or "route" in s or "arriv" in s: return "enroute"
    return "pending"

def classify(stop_type, route_name):
    st = (stop_type or "").lower()
    if "start" in st: return "start"
    if "end" in st: return "end"
    if "pickup" in st or "load" in st or "reload" in st: return "pickup"
    return "delivery"

def hhmm(v):
    v = (v or "").strip()
    if not v: return ""
    m = re.search(r"(\d{1,2}):(\d{2})", v)
    if not m: return v
    h, mn = int(m.group(1)), int(m.group(2))
    try: return datetime.time(h, mn).strftime("%-I:%M %p")
    except: return v

def build(csv_text):
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    drivers = {}     # driver name -> driver dict
    depot = None
    heat = []
    palette = ["#22d3ee", "#a78bfa", "#f59e0b", "#34d399", "#fb7185", "#60a5fa"]

    for row in rows:
        dname = col(row, "Driver name", "Driver") or "Unassigned"
        lat, lng = fnum(col(row, "Latitude", "Lat")), fnum(col(row, "Longitude", "Lng", "Long"))
        if lat is None or lng is None:
            continue
        cls = classify(col(row, "Stop Type", "Stop type"), col(row, "Route name"))
        if cls in ("start",) and depot is None:
            depot = {"lat": lat, "lng": lng, "name": col(row, "Address", "Customer name") or "Depot"}

        dv = drivers.setdefault(dname, {
            "id": "drv-" + re.sub(r"[^a-z0-9]+", "-", dname.lower()).strip("-"),
            "name": dname, "phone": col(row, "Driver phone"),
            "vehicle": col(row, "Vehicle", "Route name"),
            "color": palette[len(drivers) % len(palette)], "active": True,
            "live": None, "route": [],
        })

        status = map_status(col(row, "Delivery status", "Status"))
        photos = col(row, "Photos", "Photo", "POD")
        pod = ocr_pod(photos.split(",")[0].strip()) if (status == "completed" and photos) else None

        order_total = fnum(col(row, "Order Total", "Order total"))
        win_s, win_e = col(row, "Time window start"), col(row, "Time window end")
        arr = col(row, "Arrive time", "Arrival time")
        start = col(row, "Time window start")
        late = bool(win_e and arr and hhmm(arr) and arr > win_e)

        dv["route"].append({
            "seq": int(fnum(col(row, "Stop sequence", "Stop number")) or len(dv["route"])),
            "cls": cls, "name": col(row, "Customer name", "Location name") or "Stop",
            "addr": col(row, "Address"), "lat": lat, "lng": lng,
            "status": status,
            "arrived": hhmm(arr) if status == "completed" else None,
            "eta": hhmm(col(row, "ETA", "Arrive time") or start),
            "win_start": hhmm(win_s), "win_end": hhmm(win_e),
            "order_total": order_total, "load": fnum(col(row, "Load")),
            "timing": "late" if late else ("ontime" if status == "completed" else None),
            "missed_reason": col(row, "Missed reason") or None,
            "pod": pod,
        })
        if cls == "delivery" and order_total:
            heat.append({"lat": lat, "lng": lng, "weight": round(min(order_total / 1800.0, 1.0), 3)})

    # sort each route + infer a live position (last completed -> next pending midpoint)
    for dv in drivers.values():
        dv["route"].sort(key=lambda s: s["seq"])
        done = [s for s in dv["route"] if s["status"] == "completed"]
        enr = next((s for s in dv["route"] if s["status"] == "enroute"), None)
        anchor = enr or (done[-1] if done else (dv["route"][0] if dv["route"] else None))
        if anchor:
            dv["live"] = {"lat": anchor["lat"], "lng": anchor["lng"], "heading": 0, "speed": 0,
                          "status": "enroute" if enr else ("done" if not enr and done else "idle"),
                          "updatedAt": datetime.datetime.now().strftime("%-I:%M %p")}

    return {
        "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "market": (rows[0].get("Address", "").split(",")[1].strip() if rows and "," in rows[0].get("Address", "") else "Routes"),
        "depot": depot or {"lat": 41.4993, "lng": -81.6944, "name": "Depot"},
        "drivers": list(drivers.values()),
        "heat": heat,
        "source": "routific-export",
    }

def maybe_vrp_enrich(data):
    """Optional: re-validate planned ETAs/order via the Routific VRP API.
    Left as a clearly-marked hook — requires ROUTIFIC_API_KEY. The export already
    carries planned + actual times, so this is enrichment, not a hard dependency."""
    if not API_KEY:
        sys.stderr.write("[vrp] ROUTIFIC_API_KEY not set — using planned times from export only.\n")
        return data
    sys.stderr.write("[vrp] API key present. Planned-route enrichment hook is stubbed; "
                     "wire visit/fleet payload to POST /v1/vrp when ready.\n")
    return data

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 build_data.py <routes_export.csv | published-sheet-csv-url>")
        sys.exit(1)
    data = maybe_vrp_enrich(build(fetch_csv(sys.argv[1])))
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote data.json — {len(data['drivers'])} drivers, "
          f"{sum(len(d['route']) for d in data['drivers'])} stops, {len(data['heat'])} heat points")
