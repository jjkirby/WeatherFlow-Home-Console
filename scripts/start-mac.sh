#!/bin/bash
# Start the telemetry collector and the PiConsole window in one terminal.
set -eu

cd "$(dirname "$0")/.."
python="$PWD/.venv/bin/python"
export HOME_TELEMETRY_CONFIG="${1:-${HOME_TELEMETRY_CONFIG:-$HOME/.config/home-telemetry/govee-h5074.toml}}"

if [[ ! -x "$python" || ! -f main.py ]]; then
    echo "Install this script under scripts/ in the configured PiConsole checkout with its .venv." >&2
    exit 1
fi

collector=("$python" -m home_telemetry --config "$HOME_TELEMETRY_CONFIG")
"${collector[@]}" config validate

# Give PiConsole the same database the collector is configured to write.
HOME_TELEMETRY_DB=$("$python" - "$HOME_TELEMETRY_CONFIG" <<'PY'
import sys
import tomllib
from pathlib import Path

with open(sys.argv[1], "rb") as config:
    database = tomllib.load(config)["collector"]["database"]
print(Path(database).expanduser().resolve())
PY
)
export HOME_TELEMETRY_DB
export KIVY_METRICS_DENSITY="${KIVY_METRICS_DENSITY:-1}"
export KIVY_METRICS_FONTSCALE="${KIVY_METRICS_FONTSCALE:-1}"

"${collector[@]}" run &
collector_pid=$!
cleanup() {
    kill "$collector_pid" 2>/dev/null || true
    wait "$collector_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# Surface immediate startup errors, including an existing collector's writer lock.
sleep 1
if ! kill -0 "$collector_pid" 2>/dev/null; then
    echo "Collector exited during startup. Check its output above." >&2
    exit 1
fi
"$python" main.py
