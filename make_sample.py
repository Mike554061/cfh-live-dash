#!/usr/bin/env python3
"""Generate a realistic sample data.json so the dashboard runs before the live
Routific export / VRP key are wired in. The schema written here is exactly what
build_data.py produces from the real export — keep them in sync."""
import json, math, datetime

# Cleveland depot (matches the route-viz market).
DEPOT = {"lat": 41.4993, "lng": -81.6944, "name": "SupplyNow Cleveland Depot — 2275 E 55th St"}

def t(h, m):  # pretty time
    return datetime.time(h, m).strftime("%-I:%M %p")

# --- helper to fabricate a Firebase-style POD photo + OCR'd bill of lading ---
def pod(items, signed=True, note=""):
    return {
        "photo": "https://firebasestorage.googleapis.com/v0/b/routific-pod/o/sample-bol.jpg?alt=media",
        "signature": signed,
        "notes": note,
        "items": items,                       # OCR'd line items
        "ocrConfidence": 0.94,
        "ocrRaw": "BILL OF LADING\n" + "\n".join(f"{i['qty']}x {i['item']}" for i in items),
    }

DRIVERS = [
    {
        "id": "drv-marcus", "name": "Marcus Reed", "phone": "+12165550182",
        "vehicle": "Reefer Van 12", "color": "#22d3ee", "active": True,
        "live": {"lat": 41.4821, "lng": -81.6612, "heading": 78, "speed": 24,
                 "status": "enroute", "updatedAt": "10:42 AM"},
        "route": [
            {"seq": 0, "cls": "start", "name": "Depot — Load Up", "addr": DEPOT["name"],
             "lat": DEPOT["lat"], "lng": DEPOT["lng"], "status": "completed",
             "arrived": t(6, 5), "eta": t(6, 5), "win_start": "", "win_end": "", "order_total": None, "load": None, "pod": None},
            {"seq": 1, "cls": "delivery", "name": "Lucia's Trattoria", "addr": "1900 Murray Hill Rd, Cleveland, OH",
             "lat": 41.5095, "lng": -81.6045, "status": "completed", "arrived": t(7, 41), "eta": t(7, 38),
             "win_start": t(7, 0), "win_end": t(9, 0), "order_total": 842.50, "load": 14, "timing": "ontime",
             "pod": pod([{"item": "Roma Tomatoes 25lb", "qty": 4}, {"item": "Fresh Mozzarella 5lb", "qty": 6},
                         {"item": "00 Flour 50lb", "qty": 8}], note="Left with kitchen mgr")},
            {"seq": 2, "cls": "delivery", "name": "Eastside Grocer", "addr": "12200 Larchmere Blvd, Cleveland, OH",
             "lat": 41.4982, "lng": -81.5876, "status": "completed", "arrived": t(8, 33), "eta": t(8, 20),
             "win_start": t(8, 0), "win_end": t(8, 30), "order_total": 1340.00, "load": 22, "timing": "late",
             "pod": pod([{"item": "Whole Milk Gallon", "qty": 24}, {"item": "Large Eggs 15dz", "qty": 10},
                         {"item": "Butter 1lb", "qty": 30}], note="Dock 2")},
            {"seq": 3, "cls": "delivery", "name": "Harbor Bistro", "addr": "1146 Old River Rd, Cleveland, OH",
             "lat": 41.4969, "lng": -81.7012, "status": "enroute", "arrived": None, "eta": t(11, 5),
             "win_start": t(10, 30), "win_end": t(12, 0), "order_total": 690.25, "load": 11, "pod": None},
            {"seq": 4, "cls": "delivery", "name": "Tremont Tap House", "addr": "2572 Scranton Rd, Cleveland, OH",
             "lat": 41.4769, "lng": -81.6921, "status": "pending", "arrived": None, "eta": t(11, 48),
             "win_start": t(11, 0), "win_end": t(13, 0), "order_total": 415.00, "load": 7, "pod": None},
            {"seq": 5, "cls": "delivery", "name": "Lakewood Market Co", "addr": "14701 Detroit Ave, Lakewood, OH",
             "lat": 41.4847, "lng": -81.7993, "status": "pending", "arrived": None, "eta": t(12, 36),
             "win_start": t(12, 0), "win_end": t(14, 0), "order_total": 988.75, "load": 16, "pod": None},
        ],
    },
    {
        "id": "drv-dana", "name": "Dana Kovic", "phone": "+12165550143",
        "vehicle": "Box Truck 7", "color": "#a78bfa", "active": True,
        "live": {"lat": 41.4406, "lng": -81.7290, "heading": 200, "speed": 0,
                 "status": "idle", "updatedAt": "10:39 AM"},
        "route": [
            {"seq": 0, "cls": "start", "name": "Depot — Load Up", "addr": DEPOT["name"],
             "lat": DEPOT["lat"], "lng": DEPOT["lng"], "status": "completed", "arrived": t(6, 12), "eta": t(6, 12),
             "win_start": "", "win_end": "", "order_total": None, "load": None, "pod": None},
            {"seq": 1, "cls": "delivery", "name": "Old Brooklyn Deli", "addr": "4501 Pearl Rd, Cleveland, OH",
             "lat": 41.4376, "lng": -81.7011, "status": "completed", "arrived": t(7, 58), "eta": t(8, 0),
             "win_start": t(7, 30), "win_end": t(9, 30), "order_total": 522.40, "load": 9, "timing": "ontime",
             "pod": pod([{"item": "Pastrami 10lb", "qty": 3}, {"item": "Rye Loaf", "qty": 24}], note="")},
            {"seq": 2, "cls": "delivery", "name": "Parma Fresh Foods", "addr": "5500 Ridge Rd, Parma, OH",
             "lat": 41.3884, "lng": -81.7290, "status": "completed", "arrived": t(9, 11), "eta": t(9, 5),
             "win_start": t(9, 0), "win_end": t(10, 0), "order_total": 1755.10, "load": 28, "timing": "ontime",
             "pod": pod([{"item": "Chicken Breast 40lb", "qty": 5}, {"item": "Ground Beef 80/20 10lb", "qty": 12},
                         {"item": "Russet Potatoes 50lb", "qty": 6}], note="Signed by R. Patel")},
            {"seq": 3, "cls": "delivery", "name": "Brooklyn Heights Catering", "addr": "4700 Tiedeman Rd, Brooklyn, OH",
             "lat": 41.4346, "lng": -81.7401, "status": "missed", "arrived": None, "eta": t(10, 5),
             "win_start": t(9, 30), "win_end": t(10, 0), "order_total": 333.00, "load": 5, "timing": "late",
             "missed_reason": "Closed — no one at dock", "pod": None},
            {"seq": 4, "cls": "delivery", "name": "Independence Grill", "addr": "6700 Rockside Rd, Independence, OH",
             "lat": 41.3958, "lng": -81.6390, "status": "pending", "arrived": None, "eta": t(11, 20),
             "win_start": t(11, 0), "win_end": t(13, 0), "order_total": 612.00, "load": 10, "pod": None},
        ],
    },
    {
        "id": "drv-sam", "name": "Sam Ortega", "phone": "+12165550199",
        "vehicle": "Sprinter 3", "color": "#f59e0b", "active": True,
        "live": {"lat": 41.5612, "lng": -81.5210, "heading": 290, "speed": 31,
                 "status": "enroute", "updatedAt": "10:41 AM"},
        "route": [
            {"seq": 0, "cls": "start", "name": "Depot — Load Up", "addr": DEPOT["name"],
             "lat": DEPOT["lat"], "lng": DEPOT["lng"], "status": "completed", "arrived": t(6, 20), "eta": t(6, 20),
             "win_start": "", "win_end": "", "order_total": None, "load": None, "pod": None},
            {"seq": 1, "cls": "delivery", "name": "Euclid Family Diner", "addr": "26100 Euclid Ave, Euclid, OH",
             "lat": 41.5931, "lng": -81.5012, "status": "completed", "arrived": t(8, 5), "eta": t(8, 10),
             "win_start": t(7, 30), "win_end": t(9, 0), "order_total": 458.90, "load": 8, "timing": "ontime",
             "pod": pod([{"item": "Bacon 15lb", "qty": 4}, {"item": "Pancake Mix 25lb", "qty": 3},
                         {"item": "Maple Syrup 1gal", "qty": 6}], note="")},
            {"seq": 2, "cls": "delivery", "name": "Shoregate Cafe", "addr": "27801 Lakeshore Blvd, Euclid, OH",
             "lat": 41.6088, "lng": -81.4855, "status": "enroute", "arrived": None, "eta": t(10, 55),
             "win_start": t(10, 30), "win_end": t(12, 0), "order_total": 720.00, "load": 12, "pod": None},
            {"seq": 3, "cls": "delivery", "name": "Mentor Provisions", "addr": "7200 Center St, Mentor, OH",
             "lat": 41.6661, "lng": -81.3396, "status": "pending", "arrived": None, "eta": t(11, 50),
             "win_start": t(11, 0), "win_end": t(13, 30), "order_total": 1102.30, "load": 19, "pod": None},
        ],
    },
]

# --- delivery-density heat points (for the 3D heatmap / density modes) ---
# Weighted by completed order volume near each cluster.
HEAT = []
for d in DRIVERS:
    for s in d["route"]:
        if s["cls"] == "delivery" and s.get("order_total"):
            HEAT.append({"lat": s["lat"], "lng": s["lng"], "weight": round(s["order_total"] / 1800.0, 3)})

data = {
    "generatedAt": "2026-06-17 10:42",
    "market": "Cleveland",
    "depot": DEPOT,
    "drivers": DRIVERS,
    "heat": HEAT,
    "source": "sample",
}

with open("data.json", "w") as f:
    json.dump(data, f, indent=2)
print(f"wrote data.json — {len(DRIVERS)} drivers, "
      f"{sum(len(d['route']) for d in DRIVERS)} stops, {len(HEAT)} heat points")
