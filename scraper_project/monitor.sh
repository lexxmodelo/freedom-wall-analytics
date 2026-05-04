#!/usr/bin/env bash
# Autonomous monitor + self-healer for the Freedom Wall scraper.
# Runs forever until all targets hit 4000 posts or are skipped.

BASE="C:/Users/Alex Evan/Documents/Research/scraper_project"
LOG="$BASE/logs/AGENT_ACTIONS.log"
STDOUT_LOG="$BASE/logs/agent_stdout.log"
DATA="$BASE/data"

TARGETS=(FW-01 FW-02 FW-03 FW-04 FW-05 FW-06 FW-07 FW-08 FW-09 SLU)
TARGET_POSTS=4000
SKIP_THRESHOLD=100
STALL_CYCLES=5   # 5 × 30s = 150s stall before action
FREEZE_CYCLES=10 # 10 × 30s = 300s before kill+restart

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

is_python_alive() {
    tasklist /FI "IMAGENAME eq python.exe" 2>/dev/null | grep -qi python
}

post_count() {
    local code=$1
    local f="$DATA/${code}.jsonl"
    [[ -f "$f" ]] && wc -l < "$f" || echo 0
}

start_scraper() {
    local targets_arg="$1"
    log "LAUNCH — python main.py --cookies cookies.json --target-posts $TARGET_POSTS $targets_arg"
    cd "$BASE"
    if [[ -z "$targets_arg" ]]; then
        python main.py --cookies cookies.json --target-posts $TARGET_POSTS >> "$STDOUT_LOG" 2>&1 &
    else
        python main.py --cookies cookies.json --target-posts $TARGET_POSTS --targets $targets_arg >> "$STDOUT_LOG" 2>&1 &
    fi
    SCRAPER_PID=$!
    log "LAUNCH — PID=$SCRAPER_PID"
}

kill_scraper() {
    log "KILL — Terminating python processes"
    taskkill /F /IM python.exe /T > /dev/null 2>&1
    sleep 10
}

maintenance() {
    # Disk check
    local free_kb
    free_kb=$(df -k "$BASE" 2>/dev/null | awk 'NR==2{print $4}')
    if [[ -n "$free_kb" && "$free_kb" -lt 5242880 ]]; then
        log "DISK_WARN — Less than 5GB free (${free_kb}KB). Pausing 60s."
        sleep 60
    fi
    # Delete debug screenshots older than 1 hour
    local ss_dir="$BASE/debug_screenshots"
    if [[ -d "$ss_dir" ]]; then
        find "$ss_dir" -type f -mmin +60 -delete 2>/dev/null
    fi
    # Cookie check
    if [[ ! -f "$BASE/cookies.json" ]]; then
        log "COOKIE_MISSING — cookies.json not found! Scraper may fail."
    fi
}

# ─── Main loop ───────────────────────────────────────────────────────────────

log "MONITOR_START — Self-healing monitor started. Targets: ${TARGETS[*]}. Goal: $TARGET_POSTS posts each."

CURRENT_TARGET_IDX=0
LAST_POST_COUNT=0
STALL_COUNT=0
FREEZE_COUNT=0
MAINTENANCE_COUNTER=0
SCRAPER_PID=""

# Start scraper for all remaining targets
start_scraper ""

while true; do
    sleep 30
    MAINTENANCE_COUNTER=$((MAINTENANCE_COUNTER + 1))

    # Maintenance every 60 cycles (~30 min)
    if (( MAINTENANCE_COUNTER % 60 == 0 )); then
        maintenance
    fi

    # ── Determine which target is currently active ──────────────────────────
    # Walk through targets in order; first one under TARGET_POSTS is current
    ACTIVE_CODE=""
    ALL_DONE=true
    REMAINING_TARGETS=()

    for code in "${TARGETS[@]}"; do
        cnt=$(post_count "$code")
        if (( cnt >= TARGET_POSTS )); then
            : # done
        else
            ALL_DONE=false
            if [[ -z "$ACTIVE_CODE" ]]; then
                ACTIVE_CODE="$code"
            else
                REMAINING_TARGETS+=("$code")
            fi
        fi
    done

    if $ALL_DONE; then
        log "ALL_DONE — All ${#TARGETS[@]} targets reached $TARGET_POSTS posts. Run complete."
        exit 0
    fi

    CURRENT_COUNT=$(post_count "$ACTIVE_CODE")

    # ── Python alive check ──────────────────────────────────────────────────
    PYTHON_ALIVE=false
    is_python_alive && PYTHON_ALIVE=true

    # ── Progress check ──────────────────────────────────────────────────────
    if (( CURRENT_COUNT > LAST_POST_COUNT )); then
        RATE=$(( (CURRENT_COUNT - LAST_POST_COUNT) ))
        log "MONITOR — $ACTIVE_CODE: $CURRENT_COUNT/$TARGET_POSTS posts (+${RATE} since last check). Python=$PYTHON_ALIVE"
        LAST_POST_COUNT=$CURRENT_COUNT
        STALL_COUNT=0
        FREEZE_COUNT=0
    else
        STALL_COUNT=$((STALL_COUNT + 1))
        log "MONITOR — $ACTIVE_CODE: $CURRENT_COUNT/$TARGET_POSTS posts (no growth, stall_cycle=$STALL_COUNT). Python=$PYTHON_ALIVE"
    fi

    # ── Target reached → advance ────────────────────────────────────────────
    if (( CURRENT_COUNT >= TARGET_POSTS )); then
        log "TARGET_REACHED — $ACTIVE_CODE hit $TARGET_POSTS posts. Moving to next target."
        LAST_POST_COUNT=0
        STALL_COUNT=0
        FREEZE_COUNT=0
        # If python is still running, let it naturally move to next target
        # (main.py iterates all targets sequentially). No restart needed.
        continue
    fi

    # ── Python dead → restart ───────────────────────────────────────────────
    if ! $PYTHON_ALIVE; then
        if (( CURRENT_COUNT < SKIP_THRESHOLD && STALL_COUNT > 3 )); then
            log "SKIP — $ACTIVE_CODE has only $CURRENT_COUNT posts after retries. Skipping."
            # Mark as skipped by touching a skip file
            touch "$DATA/${ACTIVE_CODE}.skipped"
            LAST_POST_COUNT=0
            STALL_COUNT=0
        else
            log "RESTART — Python dead. $ACTIVE_CODE at $CURRENT_COUNT posts. Restarting from checkpoint."
            # Build target list: active + remaining
            local_targets=("$ACTIVE_CODE" "${REMAINING_TARGETS[@]}")
            start_scraper "${local_targets[*]}"
            LAST_POST_COUNT=$CURRENT_COUNT
            STALL_COUNT=0
            FREEZE_COUNT=0
        fi
        continue
    fi

    # ── Python alive but stalled ────────────────────────────────────────────
    if (( STALL_COUNT == STALL_CYCLES )); then
        log "STALL_WARN — $ACTIVE_CODE stalled for $((STALL_COUNT * 30))s. Watching for freeze."
    fi

    if (( STALL_COUNT >= FREEZE_CYCLES )); then
        log "FREEZE — $ACTIVE_CODE frozen for $((STALL_COUNT * 30))s. Killing and restarting."
        kill_scraper
        local_targets=("$ACTIVE_CODE" "${REMAINING_TARGETS[@]}")
        start_scraper "${local_targets[*]}"
        LAST_POST_COUNT=$CURRENT_COUNT
        STALL_COUNT=0
        FREEZE_COUNT=0
    fi

done
