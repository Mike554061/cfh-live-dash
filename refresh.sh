#!/usr/bin/env bash
# Refresh the live feed from Routific. Workspace id is baked in (not a secret);
# the API token must be supplied via the environment (never committed).
#
#   export ROUTIFIC_API_KEY='eyJ...'        # once per shell, or put in a gitignored .env
#   ./refresh.sh                            # today
#   ./refresh.sh 2026-06-10                 # a specific date
#
# Tip for continuous "live": cron it, e.g.  * * * * * cd /Users/michaelcook/pl-live-dash && ./refresh.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a   # optional local secrets file
: "${ROUTIFIC_API_KEY:?Set ROUTIFIC_API_KEY in the environment (or .env) first}"
export ROUTIFIC_WORKSPACE_ID="${ROUTIFIC_WORKSPACE_ID:-637958}"
exec python3 routific_pull.py "${1:-$(date +%F)}"
