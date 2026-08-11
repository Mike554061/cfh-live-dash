#!/usr/bin/env python3
"""Generate a SAFE, synthetic CFH demo data.json for the PUBLIC GitHub Pages build.
No real customer names, addresses, driver names, or proof-of-delivery photos — this is
what the shareable live URL serves. The real CFH feed (routific_pull.py + Telegram)
runs privately on Mike's machine and is never committed to the public repo."""
import json, datetime

def t(h, m): return datetime.time(h, m).strftime("%-I:%M %p")

def pod(sig=True):
    return {"photo": "", "signature": sig, "notes": "", "items": [], "ocrConfidence": None, "ocrRaw": ""}

def stop(seq, name, lat, lng, addr, status, **kw):
    d = {"seq": seq, "cls": "delivery", "name": name, "addr": addr, "lat": lat, "lng": lng,
         "status": status, "arrived": None, "eta": None, "win_start": "", "win_end": "",
         "order_total": None, "load": None, "order_no": None, "packages": 0, "tags": ["CFH"],
         "delivered": None, "dist_mi": None, "dwell_min": None, "drive_min": None,
         "timing": None, "missed_reason": None, "geo_ok": True, "pod": None}
    d.update(kw)
    return d

# --- Cleveland CFH route (synthetic) ---
CLE = [
    stop(1, "Lakeside Cafe Co (demo)", 41.5031, -81.6790, "1200 W 9th St, Cleveland, OH", "completed",
         delivered=t(8, 12), arrived=t(8, 9), win_start=t(7,30), win_end=t(9,0), load=16, order_no="CFH-DEMO-1041",
         packages=3, dist_mi=4.2, dwell_min=12, drive_min=18, timing="ontime", pod=pod()),
    stop(2, "Ohio City Provisions (demo)", 41.4849, -81.7020, "2700 Bridge Ave, Cleveland, OH", "completed",
         delivered=t(8, 51), arrived=t(8, 47), win_start=t(8,0), win_end=t(9,30), load=22, order_no="CFH-DEMO-1042",
         packages=5, dist_mi=2.1, dwell_min=15, drive_min=9, timing="ontime", pod=pod()),
    stop(3, "Tremont Table (demo)", 41.4772, -81.6905, "2450 Professor Ave, Cleveland, OH", "enroute",
         eta=t(10, 20), win_start=t(9,30), win_end=t(11,0), load=11, order_no="CFH-DEMO-1043",
         packages=2, dist_mi=1.6, dwell_min=None, drive_min=8),
    stop(4, "University Circle Kitchen (demo)", 41.5075, -81.6083, "11150 East Blvd, Cleveland, OH", "pending",
         eta=t(11, 5), win_start=t(10,30), win_end=t(12,0), load=18, order_no="CFH-DEMO-1044", packages=4, dist_mi=6.9),
    stop(5, "Shaker Market Hall (demo)", 41.4736, -81.5512, "20100 Chagrin Blvd, Shaker Heights, OH", "pending",
         eta=t(11, 52), win_start=t(11,0), win_end=t(13,0), load=9, order_no="CFH-DEMO-1045", packages=2, dist_mi=5.3),
]
# --- Akron CFH route (synthetic) ---
AKR = [
    stop(1, "Highland Square Deli (demo)", 41.0812, -81.5391, "780 W Market St, Akron, OH", "completed",
         delivered=t(8, 33), arrived=t(8, 30), win_start=t(8,0), win_end=t(9,30), load=13, order_no="CFH-DEMO-2071",
         packages=3, dist_mi=7.4, dwell_min=14, drive_min=22, timing="ontime", pod=pod()),
    stop(2, "Merriman Valley Grill (demo)", 41.1069, -81.5637, "1662 Merriman Rd, Akron, OH", "completed",
         delivered=t(9, 28), arrived=t(9, 12), win_start=t(8,30), win_end=t(9,0), load=20, order_no="CFH-DEMO-2072",
         packages=4, dist_mi=3.1, dwell_min=16, drive_min=11, timing="late", pod=pod()),
    stop(3, "Cuyahoga Falls Bistro (demo)", 41.1339, -81.4846, "2085 Front St, Cuyahoga Falls, OH", "enroute",
         eta=t(10, 40), win_start=t(10,0), win_end=t(11,30), load=15, order_no="CFH-DEMO-2073",
         packages=3, dist_mi=6.0, dwell_min=None, drive_min=17),
    stop(4, "Fairlawn Fresh (demo)", 41.1289, -81.6193, "3750 W Market St, Fairlawn, OH", "pending",
         eta=t(11, 34), win_start=t(11,0), win_end=t(13,0), load=12, order_no="CFH-DEMO-2074", packages=2, dist_mi=8.8),
]

def live(route, color):
    done = [s for s in route if s["status"] == "completed"]
    nxt = next((s for s in route if s["status"] == "enroute"), None)
    anchor = done[-1] if done else route[0]
    return {"lat": anchor["lat"], "lng": anchor["lng"], "heading": 90, "speed": 0,
            "status": "enroute" if nxt else "idle", "estimated": True, "updatedAt": t(10, 12)}

drivers = [
    {"id": "drv-cle", "name": "Cleveland Driver", "phone": "", "vehicle": "CFH Driver (Cleveland, OH)",
     "color": "#22d3ee", "active": True, "route": CLE, "miles": 32.4, "work_min": 268, "orders_count": 5,
     "live": live(CLE, "#22d3ee")},
    {"id": "drv-akr", "name": "Akron Driver", "phone": "", "vehicle": "CFH Driver (Akron, OH)",
     "color": "#a78bfa", "active": True, "route": AKR, "miles": 41.7, "work_min": 231, "orders_count": 4,
     "live": live(AKR, "#a78bfa")},
]
heat = [{"lat": s["lat"], "lng": s["lng"], "weight": (s["load"] or 10) / 25.0}
        for dv in drivers for s in dv["route"]]

data = {"generatedAt": "DEMO — synthetic data", "market": "CFH (Cleveland + Akron)",
        "depot": {"lat": 41.4993, "lng": -81.6944, "name": "SupplyNow Cleveland Depot"},
        "drivers": drivers, "heat": heat, "source": "cfh-demo"}

if __name__ == "__main__":
    json.dump(data, open("data.json", "w"), indent=2)
    print(f"wrote demo data.json — {len(drivers)} CFH drivers, {sum(len(d['route']) for d in drivers)} stops")
