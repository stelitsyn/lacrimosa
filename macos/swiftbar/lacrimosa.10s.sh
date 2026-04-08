#!/bin/bash
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>

# Lacrimosa Status Bar v4 — reads state.db (SQLite) + tmux sessions
# Shows per-specialist health in dropdown

DB_FILE="$HOME/.claude/lacrimosa/state.db"
RL_FILE="/tmp/lacrimosa-rl-native.json"
DASHBOARD_URL="http://localhost:1791"
PROJECT_DIR="${LACRIMOSA_PROJECT_DIR:-$HOME/your-project}"

if [ ! -f "$DB_FILE" ]; then
    echo "🔴 Lac"
    echo "---"
    echo "state.db not found | color=red"
    exit 0
fi

# Read everything in one Python call
OUTPUT=$(/usr/bin/python3 -c "
import json, os, subprocess, sqlite3, time
from datetime import datetime, timezone

db = sqlite3.connect('$DB_FILE', timeout=5)
db.row_factory = sqlite3.Row
now = datetime.now(tz=timezone.utc)

# Read state KV
state = {}
for row in db.execute('SELECT key, value FROM state'):
    state[row['key']] = json.loads(row['value'])

# Read specialist health
specs = {}
for row in db.execute('SELECT * FROM specialists'):
    specs[row['name']] = dict(row)

# Check tmux sessions
tmux_alive = {}
for name in ['conductor', 'discovery', 'engineer-triage', 'engineer-implement', 'engineer-review', 'engineer-merge', 'sentinel', 'content', 'clo', 'cfo', 'coo']:
    try:
        r = subprocess.run(['tmux', 'has-session', '-t', f'lacrimosa-{name}'],
            capture_output=True, timeout=2)
        tmux_alive[name] = r.returncode == 0
    except:
        tmux_alive[name] = False

# Per-specialist status
spec_lines = []
for name in ['conductor', 'discovery', 'engineer-triage', 'engineer-implement', 'engineer-review', 'engineer-merge', 'sentinel', 'content', 'clo', 'cfo', 'coo']:
    alive = tmux_alive.get(name, False)
    h = specs.get(name, {})
    hb = h.get('last_heartbeat', '')
    cycles = h.get('cycles_completed', 0)
    errors = h.get('consecutive_errors', 0)
    result = h.get('last_cycle_result', 'unknown')

    age_str = '—'
    if hb:
        try:
            dt = datetime.fromisoformat(hb)
            age_s = int((now - dt).total_seconds())
            if age_s < 60: age_str = f'{age_s}s ago'
            elif age_s < 3600: age_str = f'{age_s // 60}m ago'
            else: age_str = f'{age_s // 3600}h{(age_s % 3600) // 60}m ago'
        except: pass

    if alive and errors == 0:
        icon = '🟢'
        color = 'green'
    elif alive and errors > 0:
        icon = '🟡'
        color = 'orange'
    else:
        icon = '🔴'
        color = 'red'

    display = name.replace('-', ' ').title()
    spec_lines.append(f'{icon} {display} — {age_str} ({cycles} cycles) | color={color}')
    if errors > 0:
        spec_lines.append(f'  ⚠ {errors} consecutive errors | color=orange')
    if result == 'error':
        spec_lines.append(f'  Last cycle: error | color=red')

# System state
system_state = state.get('system_state', 'Unknown')

# Today counters
today = datetime.now().strftime('%Y-%m-%d')
tc_prefix = f'daily_counters.{today}'
dispatched = state.get(f'{tc_prefix}.parent_issues_dispatched', 0)
merged = state.get(f'{tc_prefix}.prs_merged', 0)
spawned = state.get(f'{tc_prefix}.workers_spawned', 0)
created = state.get(f'{tc_prefix}.issues_created', 0)

# Active count
running = sum(1 for v in tmux_alive.values() if v)
total = len(tmux_alive)

# Rate limits
rl5 = rl7 = -1
try:
    with open('$RL_FILE') as f:
        rl = json.load(f)
    rl5 = int(rl.get('five_hour_pct', -1) or -1)
    rl7 = int(rl.get('seven_day_pct', -1) or -1)
except: pass

# Overall status
if system_state == 'Stopped':
    status = 'STOPPED'
elif system_state == 'Paused':
    status = 'PAUSED'
elif running == 0:
    status = 'DOWN'
elif running < total:
    status = 'DEGRADED'
elif dispatched > 0 or spawned > 0:
    status = 'WORKING'
else:
    status = 'IDLE'

# Output as pipe-separated for bash parsing
# Line 1: title bar data
# Line 2+: specialist lines (newline separated)
print(f'{status}|{running}|{total}|{merged}|{spawned}|{dispatched}|{created}|{rl5}|{rl7}|{system_state}')
for sl in spec_lines:
    print(sl)
print('---END---')
" 2>/dev/null)

# Parse first line
FIRST_LINE=$(echo "$OUTPUT" | head -1)
IFS='|' read -r STATUS RUNNING TOTAL MERGED SPAWNED DISPATCHED CREATED RL5 RL7 SYS_STATE <<< "$FIRST_LINE"

# Specialist lines (between line 2 and ---END---)
SPEC_LINES=$(echo "$OUTPUT" | sed -n '2,/---END---/p' | sed '/---END---/d')

# Status icon
case "$STATUS" in
    WORKING)  ICON="🟢" ;;
    IDLE)     ICON="🔵" ;;
    DEGRADED) ICON="🟡" ;;
    PAUSED)   ICON="⏸️" ;;
    STOPPED)  ICON="⏹️" ;;
    DOWN)     ICON="🔴" ;;
    *)        ICON="❓" ;;
esac

# Rate limit string for title bar
RL_STR=""
RL_IND=""
if [ "$RL5" -ge 0 ] 2>/dev/null; then
    RL_STR=" ${RL5}%/${RL7}%"
    if [ "$RL5" -ge 90 ] 2>/dev/null || [ "$RL7" -ge 90 ] 2>/dev/null; then
        RL_IND=" 🔴"
    elif [ "$RL5" -ge 50 ] 2>/dev/null || [ "$RL7" -ge 80 ] 2>/dev/null; then
        RL_IND=" 🟡"
    fi
fi

# Title bar
if [ "$STATUS" = "WORKING" ]; then
    echo "$ICON ${RUNNING}/${TOTAL} ${MERGED}pr${RL_IND}${RL_STR}"
elif [ "$STATUS" = "IDLE" ]; then
    echo "$ICON ${RUNNING}/${TOTAL}${RL_IND}${RL_STR}"
elif [ "$STATUS" = "DEGRADED" ]; then
    echo "🟡 ${RUNNING}/${TOTAL}${RL_IND}${RL_STR}"
else
    echo "$ICON $STATUS${RL_IND}${RL_STR}"
fi

# ── Dropdown ──
echo "---"
echo "Lacrimosa v3 | size=14"
echo "System: $SYS_STATE | size=11 color=gray"
echo "---"

# Specialists section
echo "Specialists | size=12"
echo "$SPEC_LINES"
echo "---"

# Today's stats
echo "Today | size=12"
echo "PRs Merged: $MERGED"
echo "Workers Spawned: $SPAWNED"
echo "Issues Dispatched: $DISPATCHED"
echo "Issues Created: $CREATED"
echo "---"

# Rate Limits
if [ "$RL5" -ge 0 ] 2>/dev/null; then
    RL5_C="green"; RL7_C="green"
    [ "$RL5" -ge 50 ] && RL5_C="orange"; [ "$RL5" -ge 90 ] && RL5_C="red"
    [ "$RL7" -ge 80 ] && RL7_C="orange"; [ "$RL7" -ge 90 ] && RL7_C="red"
    echo "Rate Limits | size=12"
    echo "5h: ${RL5}% | color=$RL5_C"
    echo "7d: ${RL7}% | color=$RL7_C"
else
    echo "Rate Limits: — | color=gray"
fi
echo "---"

# Actions
echo "Attach Conductor | bash=tmux param1=attach param2=-t param3=lacrimosa-conductor terminal=true"
echo "---"
echo "Engineering | size=12"
echo "Attach Triage | bash=tmux param1=attach param2=-t param3=lacrimosa-engineer-triage terminal=true"
echo "Attach Implement | bash=tmux param1=attach param2=-t param3=lacrimosa-engineer-implement terminal=true"
echo "Attach Review | bash=tmux param1=attach param2=-t param3=lacrimosa-engineer-review terminal=true"
echo "Attach Merge | bash=tmux param1=attach param2=-t param3=lacrimosa-engineer-merge terminal=true"
echo "---"
echo "Intelligence | size=12"
echo "Attach Discovery | bash=tmux param1=attach param2=-t param3=lacrimosa-discovery terminal=true"
echo "Attach Sentinel | bash=tmux param1=attach param2=-t param3=lacrimosa-sentinel terminal=true"
echo "Attach Content | bash=tmux param1=attach param2=-t param3=lacrimosa-content terminal=true"
echo "---"
echo "C-Suite | size=12"
echo "Attach CLO | bash=tmux param1=attach param2=-t param3=lacrimosa-clo terminal=true"
echo "Attach CFO | bash=tmux param1=attach param2=-t param3=lacrimosa-cfo terminal=true"
echo "Attach COO | bash=tmux param1=attach param2=-t param3=lacrimosa-coo terminal=true"
echo "---"
echo "Attach All (11 tabs) | bash=$HOME/.claude/lacrimosa/attach-all.sh terminal=false"
echo "---"
echo "Open Dashboard | href=$DASHBOARD_URL"
echo "---"
echo "⏹ Stop All | bash=$HOME/.claude/lacrimosa/stop-all.sh terminal=false refresh=true color=red"
echo "---"
echo "Refresh | refresh=true"
