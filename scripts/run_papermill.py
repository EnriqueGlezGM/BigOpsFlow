import os
import uuid
import threading
import subprocess
import shlex
from typing import Optional
from datetime import datetime
from flask import Flask, jsonify, request


app = Flask(__name__)

# In-memory job registry (simple and good enough for dev/demo)
jobs = {}


def _run_job(job_id: str, cmd: str, cwd: Optional[str] = None):
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = datetime.utcnow().isoformat(timespec="seconds")
    jobs[job_id]["cmd"] = cmd
    try:
        # Start process and capture combined stdout+stderr
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            executable="/bin/bash",
        )
        jobs[job_id]["pid"] = proc.pid
        log_lines = []
        if proc.stdout is not None:
            for line in proc.stdout:
                log_lines.append(line)
                # Keep last ~500 lines to avoid unbounded growth
                if len(log_lines) > 500:
                    log_lines = log_lines[-500:]
                jobs[job_id]["log"] = "".join(log_lines)
        rc = proc.wait()
        jobs[job_id]["returncode"] = rc
        jobs[job_id]["ended_at"] = datetime.utcnow().isoformat(timespec="seconds")
        jobs[job_id]["status"] = "done" if rc == 0 else "error"
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["ended_at"] = datetime.utcnow().isoformat(timespec="seconds")


def _make_env_exports() -> str:
    # These envs are already present in the image, but keeping them explicit
    return (
        "export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64; "
        "export SPARK_HOME=/usr/local/spark; "
        "export PATH=\"$SPARK_HOME/bin:$PATH\"; "
        "export PYSPARK_PYTHON=python; "
        "export PYSPARK_DRIVER_PYTHON=python; "
        "export PYSPARK_SUBMIT_ARGS=\"--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.6 pyspark-shell\"; "
    )


def _script_path(name: str) -> str:
    # Scripts are mounted at /scripts in the agile container
    return f"/scripts/{name}"


def _launch_script(script_name: str):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "log": "",
    }
    script = _script_path(script_name)

    # Prefer running the script if present; fallback to inline papermill
    if os.path.exists(script):
        cmd = f"bash -lc '{shlex.quote(script)}'"
    else:
        # Fallback inline command (should not be needed if scripts exist)
        if script_name == "train.sh":
            cmd = (
                f"bash -lc '{_make_env_exports()} papermill "
                f"\"/home/jovyan/Food_delivery/Analysis.ipynb\" "
                f"\"/home/jovyan/Food_delivery/Analysis.ipynb\"'"
            )
        else:
            cmd = (
                f"bash -lc '{_make_env_exports()} papermill "
                f"\"/home/jovyan/Food_delivery/Deploying_Predictive_Systems/Make_Predictions.ipynb\" "
                f"\"/home/jovyan/Food_delivery/Deploying_Predictive_Systems/Make_Predictions.ipynb\"'"
            )

    th = threading.Thread(target=_run_job, args=(job_id, cmd), daemon=True)
    th.start()
    return job_id


def _check_token():
    token_required = os.environ.get("AGILE_SERVICE_TOKEN")
    if not token_required:
        return True
    provided = request.headers.get("X-Token") or request.args.get("token")
    return provided == token_required


@app.post("/run-train")
def run_train():
    if not _check_token():
        return jsonify({"error": "unauthorized"}), 401
    job_id = _launch_script("train.sh")
    return jsonify({"id": job_id, "status": "queued", "type": "train"})


@app.post("/run-predict")
def run_predict():
    if not _check_token():
        return jsonify({"error": "unauthorized"}), 401
    job_id = _launch_script("predict_stream.sh")
    return jsonify({"id": job_id, "status": "queued", "type": "predict"})


@app.get("/jobs/<job_id>")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not_found"}), 404
    return jsonify(job)


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Listen on 0.0.0.0:5000 (compose maps to host 5001)
    app.run(host="0.0.0.0", port=5000)
