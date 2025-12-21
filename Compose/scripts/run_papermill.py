import os
import uuid
import threading
import subprocess
import shlex
from typing import Optional
from datetime import datetime
from flask import Flask, jsonify, request


app = Flask(__name__)

# registro de jobs
jobs = {}

# Flags de características vía variables de entorno
AUTO_CHAIN_PREDICT = (os.environ.get("AUTO_CHAIN_PREDICT_AFTER_TRAIN", "true").lower() == "true")


def _run_job(job_id: str, cmd: str, cwd: Optional[str] = None):
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = datetime.utcnow().isoformat(timespec="seconds")
    jobs[job_id]["cmd"] = cmd
    try:
        # Iniciar el proceso y capturar stdout+stderr combinados
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
                # Mantener ~500 últimas líneas para evitar crecimiento ilimitado
                if len(log_lines) > 500:
                    log_lines = log_lines[-500:]
                jobs[job_id]["log"] = "".join(log_lines)
        rc = proc.wait()
        jobs[job_id]["returncode"] = rc
        jobs[job_id]["ended_at"] = datetime.utcnow().isoformat(timespec="seconds")
        jobs[job_id]["status"] = "done" if rc == 0 else "error"
        # Auto-encadenar: si el job terminado es de tipo 'train' y ha ido bien,
        # asegurar que el streaming de predicción esté corriendo.
        try:
            if rc == 0 and jobs[job_id].get("type") == "train" and AUTO_CHAIN_PREDICT:
                # ¿Hay ya un predict corriendo?
                has_running_predict = any(
                    j.get("type") == "predict" and j.get("status") == "running"
                    for j in jobs.values()
                )
                if not has_running_predict:
                    pid = _launch_script("predict_stream.sh")
                    jobs[job_id]["chained_predict_job_id"] = pid
        except Exception as _:
            # No interrumpir el flujo por errores en el encadenado
            pass
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["ended_at"] = datetime.utcnow().isoformat(timespec="seconds")


def _make_env_exports() -> str:
    return (
        "export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64; "
        "export SPARK_HOME=/usr/local/spark; "
        "export PATH=\"$SPARK_HOME/bin:$PATH\"; "
        "export PYSPARK_PYTHON=python; "
        "export PYSPARK_DRIVER_PYTHON=python; "
        "export PYSPARK_SUBMIT_ARGS=\"--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.6 pyspark-shell\"; "
    )


def _script_path(name: str) -> str:
# Los scripts se montan en /scripts en el contenedor agile
    return f"/scripts/{name}"


def _launch_script(script_name: str):
    job_type = "train" if script_name == "train.sh" else "predict"

    # Evitar duplicados: si ya hay job encolado o ejecutándose de este tipo, reutilizar su id
    for j in jobs.values():
        if j.get("type") == job_type and j.get("status") in ("queued", "running"):
            return j["id"]

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "log": "",
        "type": job_type,
    }
    script = _script_path(script_name)

    # Preferir ejecutar el script si existe; si no, usar papermill en línea
    if os.path.exists(script):
        # Ejecutar siempre vía bash para evitar depender del bit ejecutable del archivo
        cmd = f"bash -lc 'bash {shlex.quote(script)}'"
    else:
        # Comando en línea de respaldo (no debería ser necesario si existen los scripts)
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


@app.get("/jobs")
def jobs_list():
    # Devolver los jobs ordenados por created_at desc (best-effort)
    ordered = sorted(jobs.values(), key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"count": len(ordered), "jobs": ordered[:50]})


@app.get("/status/<job_type>")
def status_by_type(job_type: str):
    # Devolver si hay un job en ejecución activo del tipo dado (p. ej., 'predict' o 'train')
    active = None
    # Preferir el job en ejecución creado más recientemente
    for j in sorted(jobs.values(), key=lambda x: x.get("created_at", ""), reverse=True):
        if j.get("type") == job_type and j.get("status") == "running":
            active = j
            break
    if active:
        return jsonify({"running": True, "id": active.get("id")})
    return jsonify({"running": False})


if __name__ == "__main__":
    # Escuchar en 0.0.0.0:5000 (compose lo mapea al host 5001)
    app.run(host="0.0.0.0", port=5000)
