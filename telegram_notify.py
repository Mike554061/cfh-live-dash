#!/usr/bin/env python3
"""
Telegram delivery-completed notifications for the CFH live dashboard.

Runs right after each pull (webhook- or cron-driven). It diffs the freshly-built
data.json against a small state file and fires ONE Telegram message per newly
completed stop — account name, service time, driver arrival, driver name — with the
proof-of-delivery photo attached when present. The full POD photo + signature always
live on the dashboard; the Telegram ping is the lightweight heads-up.

CONFIG (env; token never committed):
  export TELEGRAM_BOT_TOKEN='123456:ABC...'      # from @BotFather (or reuse an existing bot)
  export TELEGRAM_CHAT_ID='11122233'             # recipient (Mike now; CFH contact later)
  export DASH_URL='https://mike554061.github.io/cfh-live-dash'   # optional deep link

USAGE:
  python3 telegram_notify.py                     # notify new completions in data.json
  python3 telegram_notify.py --test              # send a sample message and exit
"""
import json, os, sys, urllib.parse, urllib.request, mimetypes

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHAT_IDS = [c.strip() for c in CHAT_ID.split(",") if c.strip()]   # comma-separated = multiple recipients
THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID", "")   # optional: one topic thread in a group
DASH_URL = os.environ.get("DASH_URL", "")
API = "https://api.telegram.org"

def _post(method, fields, files=None):
    """Multipart POST to the Telegram Bot API (no external deps)."""
    url = f"{API}/bot{TOKEN}/{method}"
    boundary = "----cfhboundary7f3a9"
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    for k, path in (files or {}).items():
        fn = os.path.basename(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def send(text, photo_path=None):
    if not TOKEN or not CHAT_IDS:
        sys.stderr.write("[tg] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping send.\n")
        return None
    ok = None
    for cid in CHAT_IDS:                          # deliver to every recipient
        base = {"chat_id": cid, "parse_mode": "HTML"}
        if THREAD_ID:
            base["message_thread_id"] = THREAD_ID
        try:
            if photo_path and os.path.exists(photo_path):
                r = _post("sendPhoto", {**base, "caption": text}, files={"photo": photo_path})
            else:
                r = _post("sendMessage", {**base, "text": text, "disable_web_page_preview": "false"})
            ok = ok or r
        except Exception as e:
            sys.stderr.write(f"[tg] send to {cid} failed: {e}\n")
    return ok

def show_chats():
    """List chats/threads the bot can see (message the bot or add it to the CFH group first),
    so you can grab TELEGRAM_CHAT_ID (and message_thread_id for a topic)."""
    try:
        with urllib.request.urlopen(f"{API}/bot{TOKEN}/getUpdates", timeout=20) as r:
            ups = json.loads(r.read()).get("result", [])
    except Exception as e:
        return print(f"[tg] getUpdates failed: {e}")
    seen = {}
    for u in ups:
        m = u.get("message") or u.get("channel_post") or {}
        c = m.get("chat") or {}
        if c.get("id") is not None:
            seen[c["id"]] = (c.get("title") or c.get("username") or c.get("first_name") or "?",
                             c.get("type"), m.get("message_thread_id"))
    if not seen:
        return print("[tg] no chats yet — DM the bot (or add it to the CFH group and post once), then rerun.")
    for cid, (title, ctype, thread) in seen.items():
        print(f"  chat_id={cid}  type={ctype}  thread_id={thread}  «{title}»")

def completion_msg(stop, driver_name):
    win = f"{stop['win_start']} - {stop['win_end']}" if (stop.get('win_start') and stop.get('win_end')) else "—"
    lines = ["<b>✅ Delivery Completed — CFH</b>", ""]
    lines.append(f"🏢 Stop: <b>{stop.get('name','(account)')}</b>")
    lines.append(f"🕒 Service: {win}")
    lines.append(f"🚚 Driver: <b>{driver_name}</b>")
    if DASH_URL:
        lines.append(f'\n🗺️ <a href="{DASH_URL}">Open live dashboard</a>')
    return "\n".join(lines)

def key(stop):
    return str(stop.get("order_no") or f"{stop.get('name')}|{stop.get('lat')}|{stop.get('seq')}")

def notify_completions(data_path="data.json", state_path=".notified.json"):
    data = json.load(open(data_path))
    try: notified = set(json.load(open(state_path)))
    except Exception: notified = set()
    sent = 0
    for dv in data.get("drivers", []):
        for s in dv.get("route", []):
            if s.get("cls") != "delivery" or s.get("status") != "completed":
                continue
            # skip order-less depot legs — only notify real deliveries with a location
            if not (s.get("order_no") or (s.get("name") and s["name"] not in ("Stop", "Depot"))):
                continue
            k = key(s)
            if k in notified:
                continue
            if send(completion_msg(s, dv.get("name", "Driver"))) is not None:
                notified.add(k); sent += 1
    json.dump(sorted(notified), open(state_path, "w"))
    print(f"[tg] notified {sent} new completion(s); {len(notified)} total tracked")
    return sent

if __name__ == "__main__":
    if "--chatid" in sys.argv:
        show_chats()
    elif "--prime" in sys.argv:
        # mark every current completion as already-notified WITHOUT sending — run once at
        # setup so the recurring job only pings on completions that happen AFTER now.
        data = json.load(open("data.json"))
        keys = {key(s) for dv in data.get("drivers", []) for s in dv.get("route", [])
                if s.get("cls") == "delivery" and s.get("status") == "completed"}
        json.dump(sorted(keys), open(".notified.json", "w"))
        print(f"[tg] primed {len(keys)} existing completion(s) as notified (no send)")
    elif "--test" in sys.argv:
        sample = {"name": "SAMPLE — Bruno's Kitchen", "win_start": "9:00 AM", "win_end": "12:00 PM"}
        print(send(completion_msg(sample, "Chris Puskar")))
    else:
        notify_completions()
