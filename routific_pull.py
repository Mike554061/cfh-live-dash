#!/usr/bin/env python3
"""
Live pull from the Routific PLATFORM API -> data.json for the 3PL Live Dashboard.

This replaces the CSV/sheet-export path with the real API call-chain:

  GET /routes?workspaceId&date            -> routes + driver.name + timeline.uri + status
    -> GET /routes/{uuid}/timeline        -> stop sequence + planned/actual times + order uuids
       -> GET /orders/{uuid}              -> customer/location/status/POD/packages/tags/windows
          -> GET /orders/{uuid}/photos/{photoUuid}  -> raw JPEG (POD photo)  -> OCR (offline bake)

Then it infers the live driver marker by interpolating along the active leg
(last completed stop -> next stop) using elapsed-time-vs-ETA. NOTE: the Routific
API does NOT expose real-time GPS, so this position is ESTIMATED, not a GPS fix.

AUTH / CONFIG (never hard-coded — read from env):
  export ROUTIFIC_API_KEY='eyJ...'          # Company Settings > Integrations > Create API Token
  export ROUTIFIC_WORKSPACE_ID='12345'      # numeric workspace id (from the Routific dashboard URL)
  python3 routific_pull.py [YYYY-MM-DD]     # date defaults to today

OPTIONAL (offline OCR of POD bills of lading):
  pip install pillow pytesseract   &&   brew install tesseract
"""
import io, json, os, sys, math, datetime, urllib.request, urllib.error

BASE = os.environ.get("ROUTIFIC_BASE", "https://planning-service.beta.routific.com/v1")
API_KEY = os.environ.get("ROUTIFIC_API_KEY", "")
WORKSPACE_ID = os.environ.get("ROUTIFIC_WORKSPACE_ID", "")
# Only include routes whose name contains this substring (case-insensitive). For the
# CFH build set ROUTIFIC_ROUTE_FILTER=CFH -> keeps "CFH Driver (Akron/Cleveland)" only.
ROUTE_FILTER = os.environ.get("ROUTIFIC_ROUTE_FILTER", "")
DATE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ROUTIFIC_DATE", "") \
       or datetime.date.today().isoformat()

PALETTE = ["#22d3ee", "#a78bfa", "#f59e0b", "#34d399", "#fb7185", "#60a5fa"]


ORIGIN = BASE.split("/v1")[0].rstrip("/")   # scheme+host, for /v1-prefixed relative uris

def api(path, raw=False):
    """GET an API path. Returns parsed JSON, or raw bytes when raw=True.
    Handles absolute urls, /v1-prefixed relative uris (from timeline/order .uri),
    and bare paths joined onto BASE."""
    if path.startswith("http"):
        url = path
    elif path.startswith("/"):
        url = ORIGIN + path
    else:
        url = f"{BASE}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return data if raw else json.loads(data)


# ---------- field plucking (defensive — docs don't pin exact key casing) ----------
def pick(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default

def coords(order):
    loc = pick(order, "locations", "location", default=None)
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    loc = loc or {}
    lat = pick(loc, "latitude", "lat")
    lng = pick(loc, "longitude", "lng", "long")
    addr = pick(loc, "address", "name", default="")
    return (float(lat) if lat is not None else None,
            float(lng) if lng is not None else None, addr)

def time_window(order):
    tw = pick(order or {}, "timeWindows", "timeWindow", default=None)
    if isinstance(tw, list) and tw:
        tw = tw[0]
    if isinstance(tw, dict):
        return clock(tw.get("startTime") or tw.get("start")), clock(tw.get("endTime") or tw.get("end"))
    return "", ""

def clock(hhmm):
    """'09:00' -> '9:00 AM'."""
    if not hhmm:
        return ""
    try:
        h, m = str(hhmm).split(":")[:2]
        return datetime.time(int(h), int(m)).strftime("%-I:%M %p")
    except Exception:
        return str(hhmm)

def fmt_time(iso):
    if not iso:
        return None
    try:
        s = str(iso).replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s).strftime("%-I:%M %p")
    except Exception:
        return str(iso)

def parse_iso(iso):
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None

KM_TO_MI = 0.621371

def mins_between(a, b):
    da, db = parse_iso(a), parse_iso(b)
    if da and db and db >= da:
        return round((db - da).total_seconds() / 60)
    return None

def valid_pt(lat, lng):
    """Reject null / 0,0 / out-of-North-America coords so a bad geocode can't
    drag the map to the Gulf of Guinea."""
    return (lat is not None and lng is not None
            and 15 <= lat <= 72 and -170 <= lng <= -50)

def map_status(s):
    s = (s or "").lower()
    if s == "delivered":
        return "completed"
    if s == "missed":
        return "missed"
    return "pending"   # scheduled / not_scheduled  (enroute is inferred from the timeline)

def bearing(a, b):
    if not a or not b:
        return 0
    (lat1, lng1), (lat2, lng2) = a, b
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------- offline OCR ----------
_OCR = None
def ocr_ready():
    global _OCR
    if _OCR is None:
        try:
            import pytesseract, PIL  # noqa
            _OCR = True
        except Exception:
            _OCR = False
            sys.stderr.write("[ocr] pytesseract/Pillow missing — photos kept, OCR skipped.\n")
    return _OCR

import re
ITEM_RE = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.{3,60}?)\s*$")
def ocr_bytes(img_bytes):
    if not ocr_ready():
        return {"items": [], "ocrConfidence": None, "ocrRaw": "", "signature": None, "notes": ""}
    try:
        import pytesseract
        from PIL import Image
        raw = pytesseract.image_to_string(Image.open(io.BytesIO(img_bytes)))
        items = [{"item": m.group(2).strip(), "qty": int(m.group(1))}
                 for m in (ITEM_RE.match(l) for l in raw.splitlines()) if m]
        return {"items": items, "ocrConfidence": 0.9 if items else 0.4,
                "ocrRaw": raw.strip(), "signature": None, "notes": ""}
    except Exception as e:
        sys.stderr.write(f"[ocr] failed: {e}\n")
        return {"items": [], "ocrConfidence": None, "ocrRaw": "", "signature": None, "notes": ""}


def build_pod(order, order_uuid):
    """Download POD photos (binary) + OCR. proofOfDelivery.photos may be a list of
    {uuid:..} objects or plain urls; handle both."""
    pod = pick(order, "proofOfDelivery", default=None)
    if not pod:
        return None
    photos = pod.get("photos") or []
    photo_url, ocr = None, {"items": [], "ocrConfidence": None, "ocrRaw": "", "notes": ""}
    if photos:
        first = photos[0]
        try:
            if isinstance(first, dict) and first.get("uuid"):
                img = api(f"orders/{order_uuid}/photos/{first['uuid']}", raw=True)
            else:                                   # already a URL
                img = api(str(first), raw=True)
            os.makedirs("pod", exist_ok=True)
            photo_url = f"pod/{order_uuid}.jpg"
            with open(photo_url, "wb") as f:
                f.write(img)
            ocr = ocr_bytes(img)
        except Exception as e:
            sys.stderr.write(f"[pod] photo fetch failed for {order_uuid}: {e}\n")
    return {"photo": photo_url, "signature": bool(pod.get("signature")),
            "notes": ocr.get("notes", ""), "items": ocr["items"],
            "ocrConfidence": ocr["ocrConfidence"], "ocrRaw": ocr["ocrRaw"]}


def fetch_timeline(route):
    """Walk the (paginated) timeline -> ordered list of stop dicts."""
    uri = pick(pick(route, "timeline", default={}) or {}, "uri") or \
          f"routes/{pick(route,'uuid')}/timeline"
    stops, page = [], uri
    while page:
        tl = api(page)
        for st in (tl.get("data") or tl.get("stops") or tl.get("items") or []):
            stops.append(st)
        page = (tl.get("metadata") or {}).get("nextPage") or tl.get("nextPage")
    return stops


def build():
    if not API_KEY:
        sys.exit("ERROR: set ROUTIFIC_API_KEY in the environment.")
    if not WORKSPACE_ID:
        sys.exit("ERROR: set ROUTIFIC_WORKSPACE_ID (numeric, from your Routific dashboard).")

    routes_resp = api(f"routes?workspaceId={WORKSPACE_ID}&date={DATE}")
    routes = (routes_resp.get("data") or routes_resp.get("routes")) \
        if isinstance(routes_resp, dict) else routes_resp
    drivers, heat, depot = [], [], None

    for i, route in enumerate(routes or []):
        rname = pick(route, "name", default="")
        if ROUTE_FILTER and ROUTE_FILTER.lower() not in rname.lower():
            continue   # e.g. keep only "CFH …" routes
        dname = pick(pick(route, "driver", default={}) or {}, "name", default="Unassigned")
        dv = {"id": "drv-" + re.sub(r"[^a-z0-9]+", "-", dname.lower()).strip("-") or f"drv-{i}",
              "name": dname, "phone": "", "vehicle": pick(route, "name", default=""),
              "color": PALETTE[i % len(PALETTE)], "active": True, "live": None, "route": []}

        order_cache = {}
        for seq, st in enumerate(fetch_timeline(route)):
            stype = (pick(st, "type") or "").lower()
            cls = ("start" if "start" in stype else "end" if "end" in stype
                   else "pickup" if "pickup" in stype else "delivery")
            order_refs = st.get("orders") or []
            order = None
            if order_refs:
                ou = pick(order_refs[0], "uuid", "uri")
                ou = ou.rstrip("/").split("/")[-1] if ou else None
                if ou:
                    order = order_cache.get(ou) or api(f"orders/{ou}")
                    order_cache[ou] = order
            lat, lng, addr = coords(order or {})
            if cls in ("start", "end") and (lat is None):
                continue
            if cls == "start" and depot is None and lat is not None:
                depot = {"lat": lat, "lng": lng, "name": addr or "Depot"}

            status = map_status(pick(order or {}, "status")) if order else "completed"
            actual_arr = pick(st, "actualArrivalTime")
            planned_arr = pick(st, "plannedArrivalTime")
            win_s, win_e = time_window(order)
            stop = {
                "seq": seq, "cls": cls,
                "name": pick(order or {}, "name", default=("Depot" if cls in ("start", "end") else "Stop")),
                "addr": addr, "lat": lat, "lng": lng, "status": status,
                "arrived": fmt_time(actual_arr) if status == "completed" else None,
                "eta": fmt_time(planned_arr),
                "win_start": win_s, "win_end": win_e,
                "order_total": None,
                "load": pick(order or {}, "load"),
                "order_no": pick(order or {}, "customerOrderNumber", "displayOrderId", "routificOrderNumber"),
                "packages": len(pick(order or {}, "packages", default=[]) or []),
                "tags": pick(order or {}, "tags", default=[]) or [],
                "delivered": fmt_time(pick(order or {}, "deliveryTime")) if status == "completed" else None,
                "timing": "late" if (planned_arr and actual_arr and str(actual_arr) > str(planned_arr) and status == "completed") else ("ontime" if status == "completed" else None),
                "missed_reason": pick(order or {}, "deliveryMissedReason"),
                "dist_mi": round(pick(st, "distanceFromPreviousStopInKilometers", default=0) * KM_TO_MI, 1)
                           if pick(st, "distanceFromPreviousStopInKilometers") is not None else None,
                "dwell_min": mins_between(actual_arr, pick(st, "actualDepartureTime"))
                             or mins_between(planned_arr, pick(st, "plannedDepartureTime")),
                "drive_min": None,   # filled in the pass below (this arrival − previous departure)
                "geo_ok": valid_pt(lat, lng),
                "pod": build_pod(order, pick(order, "uuid") or "") if (order and status == "completed") else None,
                "_actual_arr": actual_arr, "_actual_dep": pick(st, "actualDepartureTime"),
                "_planned_arr": planned_arr,
            }
            dv["route"].append(stop)
            if cls == "delivery" and valid_pt(lat, lng):
                heat.append({"lat": lat, "lng": lng, "weight": 0.5})

        # drive time per leg = this stop's arrival − previous stop's departure
        prev_dep = None
        for s in dv["route"]:
            s["drive_min"] = mins_between(prev_dep, s.get("_actual_arr") or s.get("_planned_arr"))
            prev_dep = s.get("_actual_dep") or s.get("_planned_arr")
        # route summary (from the routes-list object)
        dv["miles"] = round((pick(route, "distanceInKilometers", default=0) or 0) * KM_TO_MI, 1)
        dv["work_min"] = round((pick(route, "workingTimeInSeconds", default=0) or 0) / 60)
        dv["orders_count"] = pick(route, "ordersCount", default=None)

        infer_live(dv)
        for s in dv["route"]:          # strip internal helpers
            for k in ("_actual_arr", "_actual_dep", "_planned_arr"):
                s.pop(k, None)
        drivers.append(dv)

    if depot is None:   # start_location carries no coords; fall back to first delivery
        for dv in drivers:
            p = next((s for s in dv["route"] if valid_pt(s["lat"], s["lng"])), None)
            if p:
                depot = {"lat": p["lat"], "lng": p["lng"], "name": "Fleet origin"}
                break
    return {"generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "market": DATE, "depot": depot or {"lat": 41.4993, "lng": -81.6944, "name": "Depot"},
            "drivers": drivers, "heat": heat, "source": "routific-platform-api"}


def infer_live(dv):
    """Mark the first not-completed delivery as 'enroute' and interpolate the marker
    along the leg from the last completed stop using elapsed-vs-ETA (NOT GPS)."""
    route = dv["route"]
    done = [s for s in route if s["status"] == "completed" and valid_pt(s["lat"], s["lng"])]
    nxt = next((s for s in route if s["status"] == "pending" and s["cls"] == "delivery"
                and valid_pt(s["lat"], s["lng"])), None)
    if nxt:
        nxt["status"] = "enroute"
    # anchor on the last completed stop that has coords; else the first stop with coords
    last = done[-1] if done else next((s for s in route if valid_pt(s["lat"], s["lng"])), None)
    if not last:
        return
    pos = (last["lat"], last["lng"])
    head = 0
    if nxt and nxt["lat"] is not None:
        dep = parse_iso(last.get("_actual_dep")) or parse_iso(last.get("_actual_arr"))
        eta = parse_iso(nxt.get("_planned_arr"))
        now = datetime.datetime.now(dep.tzinfo) if dep and dep.tzinfo else datetime.datetime.now()
        frac = 0.0
        if dep and eta and eta > dep:
            frac = max(0.0, min(1.0, (now - dep).total_seconds() / (eta - dep).total_seconds()))
        pos = (last["lat"] + (nxt["lat"] - last["lat"]) * frac,
               last["lng"] + (nxt["lng"] - last["lng"]) * frac)
        head = bearing((last["lat"], last["lng"]), (nxt["lat"], nxt["lng"]))
    dv["live"] = {"lat": pos[0], "lng": pos[1], "heading": round(head),
                  "speed": 0, "status": "enroute" if nxt else ("done" if done else "idle"),
                  "estimated": True,   # flag: interpolated, not a GPS fix
                  "updatedAt": datetime.datetime.now().strftime("%-I:%M %p")}


if __name__ == "__main__":
    data = build()
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote data.json for {DATE} — {len(data['drivers'])} drivers, "
          f"{sum(len(d['route']) for d in data['drivers'])} stops")
