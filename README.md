# CFH Live Delivery Dashboard + Telegram

Customer-facing **"where is my CFH delivery right now"** dashboard for SupplyNow's CFH routes,
merged with **Telegram delivery-completed notifications**. Built for the CFH route review
(Fall 2026 / Winter 2027).

- **Live URL (GitHub Pages):** serves the app with **synthetic demo data** — safe to share.
- **Dashboard:** satellite-globe map, CFH driver positions, completed-vs-upcoming stops, stop list
  with dwell/distance, route playback, and the **proof-of-delivery photo + digital signature** in a
  click-to-enlarge detail window. Map modes: satellite / heatmap / 3D density / flow.
- **Telegram:** when a CFH stop is delivered, a notification fires with **account name, service time,
  driver arrival, and driver name** (POD photo attached when available). The full POD photo + signature
  live on the dashboard.

## Two halves

| | Where it runs | Data |
|---|---|---|
| **Public dashboard** | GitHub Pages (this repo) | `data.json` = synthetic CFH demo (`cfh_sample.py`) |
| **Real feed + Telegram** | Privately on Mike's machine | Routific Platform API, filtered to CFH routes |

The real feed is intentionally **not** committed — a public repo exposes whatever it contains, so real
customer names, addresses, driver names, and delivery photos stay private.

## Run the real feed (private)

```bash
export ROUTIFIC_API_KEY='eyJ...'          # Routific Platform API token
export ROUTIFIC_WORKSPACE_ID='637958'
export ROUTIFIC_ROUTE_FILTER='CFH'        # keep only "CFH Driver (...)" routes
export TELEGRAM_BOT_TOKEN='...'           # DEDICATED CFH bot (from @BotFather), not the shared one
export TELEGRAM_CHAT_ID='...'             # the one CFH thread/group all pings land in
export TELEGRAM_THREAD_ID='...'           # optional: a specific topic thread inside that group
export DASH_URL='https://mike554061.github.io/cfh-live-dash'

python3 routific_pull.py 2026-06-05       # build CFH-only data.json (+ downloads POD photos)
python3 telegram_notify.py                # fire Telegram for any newly completed CFH stops
# or, push-driven:
python3 webhook_server.py                 # Routific webhooks -> refresh -> Telegram (see below)
```

`webhook_server.py` receives the three Routific webhooks (Route Published, Route ETAs Updated,
Order Status Updated), debounces, re-pulls CFH data, and fires Telegram for new completions.
Expose with `ngrok http 4191` and register the URLs in Routific → Integrations.

### Dedicated CFH bot (one thread)
CFH gets its **own** Telegram bot and a **single thread**, separate from the general SupplyNow bot:
1. In Telegram, message **@BotFather** → `/newbot` → name it (e.g. `CFH Deliveries`) → copy the token.
2. Create the CFH group/channel (the "one thread"), add the new bot, and post any message in it.
3. Run `python3 telegram_notify.py --chatid` to print the `chat_id` (and `thread_id` for a topic).
4. Set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_THREAD_ID` and you're live.

(The initial proof-of-life ping was sent via the existing @supplynowdeliverybot to Mike's DM; the
production feed will use the dedicated CFH bot above.)

## Files
- `index.html` — the dashboard (self-contained, no build step)
- `routific_pull.py` — Routific Platform API → `data.json` (CFH filter, POD download, metrics, live-marker interp)
- `telegram_notify.py` — delivery-completed Telegram notifier (diffs new completions, attaches POD)
- `webhook_server.py` — Routific webhook receiver → refresh → notify
- `cfh_sample.py` — generates the synthetic public demo `data.json`
