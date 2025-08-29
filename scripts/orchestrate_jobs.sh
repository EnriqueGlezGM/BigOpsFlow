#!/usr/bin/env bash
set -euo pipefail

# Orchestrates: wait for agile microservice -> run train -> wait done -> run predict

AGILE_BASE="http://localhost:5000"
TOKEN_HEADER=""

if [ -n "${AGILE_SERVICE_TOKEN:-}" ]; then
  TOKEN_HEADER="-H X-Token:${AGILE_SERVICE_TOKEN}"
fi

log() { printf "[%s] %s\n" "$(date -u +%FT%T)" "$*"; }

wait_health() {
  log "Waiting for agile microservice at ${AGILE_BASE}/healthz ..."
  until curl -fsS ${TOKEN_HEADER} "${AGILE_BASE}/healthz" >/dev/null; do sleep 2; done
  log "Agile microservice is healthy."
}

post_json() {
  # $1: path
  curl -fsS -X POST ${TOKEN_HEADER} "${AGILE_BASE}$1"
}

get_json() {
  # $1: path
  curl -fsS ${TOKEN_HEADER} "${AGILE_BASE}$1"
}

parse_json_field() {
  # Read JSON from stdin and extract field via Python (jq may not be present)
  # $1: field name
  python - "$1" <<'PY'
import sys, json
field = sys.argv[1]
data = json.load(sys.stdin)
print(data.get(field, ""))
PY
}

latest_job_id_by_type() {
  # $1: type (train|predict)
  type="$1"
  get_json "/jobs" | python - "$type" <<'PY'
import sys, json
job_type = sys.argv[1]
data = json.load(sys.stdin)
jobs = data.get('jobs', [])
for j in jobs:  # already ordered desc by server
    if j.get('type') == job_type:
        print(j.get('id',''))
        break
PY
}

job_status_by_id() {
  # $1: id
  get_json "/jobs/$1" | python - <<'PY'
import sys, json
data = json.load(sys.stdin)
print(data.get('status',''))
PY
}

main() {
  wait_health

  log "Triggering training job ..."
  train_json=$(post_json "/run-train" || true)
  if [ -z "${train_json}" ]; then
    log "WARN: Couldn't start training (empty response). Will try to infer job id."
  fi
  train_id=$(printf '%s' "${train_json}" | parse_json_field id || true)
  if [ -z "${train_id}" ]; then
    log "INFO: Attempting to detect latest train job id from /jobs ..."
    # Give it a moment to register
    sleep 1
    train_id=$(latest_job_id_by_type train || true)
  fi
  if [ -n "${train_id}" ]; then
    log "Training job id: ${train_id}. Waiting for completion ..."
  else
    log "WARN: Could not determine a training job id. Will wait for any train job to finish by listing."
  fi

  # Poll status until done/error
  # Wait up to ~20 minutes (adjust as needed)
  max_tries=400
  tries=0
  while true; do
    sleep 3
    tries=$((tries+1))
    # First preference: if we know the id, query it directly
    if [ -n "${train_id}" ]; then
      status_json=$(get_json "/jobs/${train_id}" || true)
      if [ -n "${status_json}" ]; then
        status=$(printf '%s' "${status_json}" | parse_json_field status || true)
        if [ -n "${status}" ]; then
          log "Train status: ${status}"
          if [ "${status}" = "done" ]; then
            break
          elif [ "${status}" = "error" ]; then
            log "ERROR: Training job failed. Will not trigger predict."
            exit 1
          fi
        fi
      fi
    else
      # Fallback: see if any train job appears and completes
      latest=$(latest_job_id_by_type train || true)
      if [ -n "$latest" ]; then
        train_id="$latest"
        log "Detected train job id: ${train_id}"
      fi
    fi
    if [ "$tries" -ge "$max_tries" ]; then
      log "ERROR: Timeout waiting for training to finish."
      exit 1
    fi
  done

  log "Triggering predict (stream) job ..."
  attempts=0
  max_attempts=3
  while [ $attempts -lt $max_attempts ]; do
    attempts=$((attempts+1))
    pjson=$(post_json "/run-predict" || true)
    pid=$(printf '%s' "$pjson" | parse_json_field id || true)
    if [ -z "$pid" ]; then
      # try to infer latest predict job id
      sleep 1
      pid=$(latest_job_id_by_type predict || true)
    fi
    if [ -n "$pid" ]; then
      log "Predict job id: $pid"
    fi
    # Verify running
    sleep 2
    sjson=$(get_json "/status/predict" || true)
    running=$(printf '%s' "$sjson" | parse_json_field running || true)
    if [ "$running" = "True" ] || [ "$running" = "true" ]; then
      log "Predict job is running."
      break
    fi
    # Also check job state directly
    if [ -n "$pid" ]; then
      pstate=$(job_status_by_id "$pid" || true)
      [ -n "$pstate" ] && log "Predict state: $pstate"
      if [ "$pstate" = "running" ]; then
        log "Predict job reported running by job status."
        break
      fi
    fi
    log "WARN: Predict not running yet (attempt ${attempts}/${max_attempts}). Retrying in 3s ..."
    sleep 3
  done
  if [ $attempts -ge $max_attempts ]; then
    log "ERROR: Failed to ensure predict is running after ${max_attempts} attempts."
  fi
}

main "$@"
