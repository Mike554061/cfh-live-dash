#!/usr/bin/env python3
"""
Routific webhook receiver -> triggers a live data.json refresh (push instead of polling).

Routific Platform API offers three webhooks (Company Settings > Integrations > Webhooks):
  • Route Published        — a route was published / re-published
  • Route ETAs Updated     — ETAs recalculated mid-route (the closest thing to "live")
  • Order Status Updated   — a stop went delivered / missed

Point all three at this server. Each event (re)schedules a single debounced refresh
(`routific_pull.py`), so a burst of order-status events collapses into one pull. The
dashboard then picks the new data.json up on its normal poll.

RUN:
  export ROUTIFIC_API_KEY='eyJ...'
  export ROUTIFIC_WORKSPACE_ID='637958'
  export ROUTIFIC_WEBHOOK_SECRET='optional-shared-secret'   # if set, required on requests
  python3 webhook_server.py                                  # listens on :4191

EXPOSE (webhooks need a public URL):
  ngrok http 4191      # then register https://<id>.ngrok.app/webhooks/<event> in Routific

ENDPOINTS (any of these accept POST; the path just labels the event in logs):
  /webhooks/route-published
  /webhooks/etas-updated
  /webhooks/order-status
  /webhooks            (catch-all)
  /health              (GET — liveness check)
"""
import json, os, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("WEBHOOK_PORT", "4191"))
SECRET = os.environ.get("ROUTIFIC_WEBHOOK_SECRET", "")
DEBOUNCE_SECONDS = float(os.environ.get("WEBHOOK_DEBOUNCE", "3"))
HERE = os.path.dirname(os.path.abspath(__file__))

_lock = threading.Lock()
_timer = None          # pending debounced refresh
_last_run = 0.0


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_refresh(date=None):
    global _last_run
    with _lock:
        _last_run = time.time()
    args = [sys.executable, os.path.join(HERE, "routific_pull.py")]
    if date:
        args.append(date)
    log(f"refreshing data.json {('for '+date) if date else '(today)'} …")
    try:
        out = subprocess.run(args, cwd=HERE, capture_output=True, text=True, timeout=600)
        if out.returncode == 0:
            log("refresh ok: " + (out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "done"))
            # fire Telegram for any newly-completed stops (no-op if TELEGRAM_* unset)
            try:
                tg = subprocess.run([sys.executable, os.path.join(HERE, "telegram_notify.py")],
                                    cwd=HERE, capture_output=True, text=True, timeout=120)
                if tg.stdout.strip():
                    log(tg.stdout.strip().splitlines()[-1])
            except Exception as e:
                log(f"telegram notify error: {e}")
        else:
            log("refresh FAILED: " + (out.stderr.strip()[-300:] or "unknown"))
    except Exception as e:
        log(f"refresh error: {e}")


def schedule_refresh(date=None):
    """Coalesce bursts: (re)arm a single timer that fires after DEBOUNCE_SECONDS quiet."""
    global _timer
    with _lock:
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE_SECONDS, run_refresh, kwargs={"date": date})
        _timer.daemon = True
        _timer.start()


def event_date(payload):
    """Best-effort: pull a date out of the webhook payload so we refresh the right day."""
    for k in ("date", "deliveryDate", "routeDate"):
        if isinstance(payload, dict) and payload.get(k):
            return str(payload[k])[:10]
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body="ok"):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": body}).encode())

    def log_message(self, *a):
        pass  # quiet the default access log; we log our own

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, "alive")
        self._send(404, "not found")

    def do_POST(self):
        if not self.path.startswith("/webhooks"):
            return self._send(404, "not found")
        # optional shared-secret check (header or ?secret=)
        if SECRET:
            supplied = self.headers.get("X-Routific-Secret") or self.headers.get("Authorization", "")
            if SECRET not in (supplied, supplied.replace("Bearer ", "")):
                log(f"rejected {self.path} — bad/missing secret")
                return self._send(401, "unauthorized")
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {}
        event = self.path.rsplit("/", 1)[-1] or "webhook"
        log(f"event '{event}' received ({len(raw)}B) — scheduling refresh")
        schedule_refresh(event_date(payload))
        self._send(200, "accepted")  # ack fast; refresh happens async + debounced


if __name__ == "__main__":
    if not os.environ.get("ROUTIFIC_API_KEY"):
        sys.exit("ERROR: set ROUTIFIC_API_KEY (and ROUTIFIC_WORKSPACE_ID) before starting.")
    os.environ.setdefault("ROUTIFIC_WORKSPACE_ID", "637958")
    log(f"webhook receiver on :{PORT}  (debounce {DEBOUNCE_SECONDS}s"
        f"{', secret required' if SECRET else ', no secret'})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
