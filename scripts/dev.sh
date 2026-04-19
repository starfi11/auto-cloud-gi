#!/usr/bin/env bash
# scripts/dev.sh — debugging shortcuts for auto-cloud-gi.
# Wraps scripts/remote_ctl.py, caches last run id, runs project tests via .venv.
#
# Config (env vars; no secrets baked into the script):
#   REMOTE_HOST      host[:port]     default 127.0.0.1:8788
#   REMOTE_TOKEN     X-API-Token     default empty (auth off on server)
#   REMOTE_TIMEOUT   seconds         default 5
#   PY               python path     default .venv/bin/python
#
# These can be exported in the shell, passed inline, or placed in
# scripts/.dev.env (gitignored, auto-sourced). See scripts/.dev.env.example.

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f scripts/.dev.env ]]; then
  set -a; . scripts/.dev.env; set +a
fi

PY="${PY:-$ROOT/.venv/bin/python}"
CTL=("$PY" "$ROOT/scripts/remote_ctl.py")
LAST_FILE="$ROOT/runtime/tmp/last_run"
mkdir -p "$(dirname "$LAST_FILE")"

pick_id() {
  if [[ -n "${1:-}" ]]; then printf '%s\n' "$1"; return; fi
  if [[ -s "$LAST_FILE" ]]; then cat "$LAST_FILE"; return; fi
  echo "error: no run_id given and no cached id at $LAST_FILE" >&2
  exit 2
}

save_id() { printf '%s' "$1" > "$LAST_FILE"; }

usage() {
  cat <<'EOF'
Usage: scripts/dev.sh <command> [args]

Config (env vars; optionally in scripts/.dev.env):
  REMOTE_HOST     host[:port]     default 127.0.0.1:8788
  REMOTE_TOKEN    X-API-Token     default empty
  REMOTE_TIMEOUT  seconds         default 5
  PY              python path     default .venv/bin/python

Commands:
  env                       Print resolved config (token redacted)
  test [extra-args]         .venv/bin/python -m unittest discover -s tests [args]

  health                    GET /api/v1/health
  pull [branch]             POST /api/v1/system/git/pull (origin + optional branch)
  runs [status]             List runs; optional status filter

  start [profile] [scenario] [trigger]
                            Start a run (defaults: genshin_cloud_bettergi /
                            daily_default / CLI_TRIGGER). Caches run id.
  dry   [profile] [scenario]  Dry-run version of start; does not cache id.

  last                      Print cached last run id
  id <run_id>               Set the cached run id

  brief  [run_id]           show (no diagnostics) — quick status/progress
  show   [run_id]           show --include summary,diagnostics
  states [run_id]           tail --stream state_transitions
  actions [run_id]          tail --stream actions
  events [run_id]           tail --stream events
  follow [run_id] [stream]  tail --follow (stream default: events)
  wait   [run_id] [interval=2s]
                            Poll status until terminal; print final status.

  frames [run_id]           List diagnostic frames
  fetch  [run_id] <name>    Download frame to runtime/debug/<run_id>/<name>

  interrupt [run_id] [reason]
  risk      [run_id] [reason]

Run id defaults to the cached value when omitted.
EOF
}

cmd_env() {
  local tok_display="(unset)"
  if [[ -n "${REMOTE_TOKEN:-}" ]]; then
    tok_display="<redacted ${#REMOTE_TOKEN} chars>"
  fi
  cat <<EOF
REMOTE_HOST=${REMOTE_HOST:-127.0.0.1:8788}
REMOTE_TOKEN=$tok_display
REMOTE_TIMEOUT=${REMOTE_TIMEOUT:-5}
PY=$PY
last_run=$(cat "$LAST_FILE" 2>/dev/null || echo '-')
EOF
}

cmd_test() { exec "$PY" -m unittest discover -s tests "$@"; }

cmd_health() { "${CTL[@]}" health; }
cmd_pull() {
  local branch="${1:-}"
  if [[ -n "$branch" ]]; then
    "${CTL[@]}" pull --branch "$branch"
  else
    "${CTL[@]}" pull
  fi
}

cmd_runs() {
  if [[ -n "${1:-}" ]]; then
    "${CTL[@]}" runs --status "$1"
  else
    "${CTL[@]}" runs
  fi
}

cmd_start() {
  local profile="${1:-genshin_cloud_bettergi}"
  local scenario="${2:-daily_default}"
  local trigger="${3:-CLI_TRIGGER}"
  local idem="cli-$(date +%s)-$$"
  local out
  out=$("${CTL[@]}" start --profile "$profile" --scenario "$scenario" --trigger "$trigger" --idem "$idem")
  printf '%s\n' "$out"
  local id
  id=$(printf '%s' "$out" | "$PY" -c 'import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
rid = d.get("run_id") or d.get("receipt", {}).get("run_id", "")
print(rid or "")
' 2>/dev/null || true)
  if [[ -n "$id" ]]; then
    save_id "$id"
    echo "saved last_run=$id" >&2
  fi
}

cmd_dry() {
  local profile="${1:-genshin_cloud_bettergi}"
  local scenario="${2:-daily_default}"
  "${CTL[@]}" start --dry-run --profile "$profile" --scenario "$scenario" --idem "cli-dry-$(date +%s)-$$"
}

cmd_last() {
  if [[ -s "$LAST_FILE" ]]; then cat "$LAST_FILE"; echo; else
    echo "no cached run id at $LAST_FILE" >&2; exit 2
  fi
}

cmd_id() {
  [[ -z "${1:-}" ]] && { echo "usage: dev.sh id <run_id>" >&2; exit 2; }
  save_id "$1"
  echo "saved last_run=$1"
}

cmd_show()    { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" show "$id" --include summary,diagnostics; }
cmd_brief()   { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" show "$id"; }
cmd_states()  { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" tail "$id" --stream state_transitions --limit 2000; }
cmd_actions() { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" tail "$id" --stream actions --limit 2000; }
cmd_events()  { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" tail "$id" --stream events --limit 2000; }

cmd_follow() {
  local id; id=$(pick_id "${1:-}")
  local stream="${2:-events}"
  "${CTL[@]}" tail "$id" --stream "$stream" --follow
}

cmd_wait() {
  local id; id=$(pick_id "${1:-}")
  local interval="${2:-2}"
  while :; do
    local json status
    json=$("${CTL[@]}" show "$id" 2>/dev/null || true)
    status=$(printf '%s' "$json" | "$PY" -c 'import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
run = d.get("run") if isinstance(d.get("run"), dict) else d
print(run.get("status", "") if isinstance(run, dict) else "")
' 2>/dev/null || true)
    if [[ -z "$status" ]]; then
      echo "error: cannot read status for $id" >&2; exit 2
    fi
    printf '%s %s\n' "$(date +%H:%M:%S)" "$status" >&2
    case "$status" in
      succeeded|failed|interrupted|risk_escalated|aborted|cancelled)
        printf '%s\n' "$status"; return 0 ;;
    esac
    sleep "$interval"
  done
}

cmd_frames() { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" frames "$id"; }

cmd_fetch() {
  local id; id=$(pick_id "${1:-}")
  local name="${2:-}"
  [[ -z "$name" ]] && { echo "usage: dev.sh fetch [run_id] <name>" >&2; exit 2; }
  local out="$ROOT/runtime/debug/$id/$name"
  case "$out" in
    *.png|*.jpg|*.jpeg|*.webp) ;;
    *) out="$out.png" ;;
  esac
  mkdir -p "$(dirname "$out")"
  "${CTL[@]}" frame "$id" "$name" -o "$out"
}

cmd_interrupt() { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" interrupt "$id" --reason "${2:-cli}"; }
cmd_risk()      { local id; id=$(pick_id "${1:-}"); "${CTL[@]}" risk      "$id" --reason "${2:-cli}"; }

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    ""|-h|--help|help) usage ;;
    env)        cmd_env       "$@" ;;
    test)       cmd_test      "$@" ;;
    health)     cmd_health    "$@" ;;
    pull)       cmd_pull      "$@" ;;
    runs)       cmd_runs      "$@" ;;
    start)      cmd_start     "$@" ;;
    dry)        cmd_dry       "$@" ;;
    last)       cmd_last      "$@" ;;
    id)         cmd_id        "$@" ;;
    show)       cmd_show      "$@" ;;
    brief)      cmd_brief     "$@" ;;
    states)     cmd_states    "$@" ;;
    actions)    cmd_actions   "$@" ;;
    events)     cmd_events    "$@" ;;
    follow)     cmd_follow    "$@" ;;
    wait)       cmd_wait      "$@" ;;
    frames)     cmd_frames    "$@" ;;
    fetch)      cmd_fetch     "$@" ;;
    interrupt)  cmd_interrupt "$@" ;;
    risk)       cmd_risk      "$@" ;;
    *)
      echo "unknown command: $cmd" >&2
      echo >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
