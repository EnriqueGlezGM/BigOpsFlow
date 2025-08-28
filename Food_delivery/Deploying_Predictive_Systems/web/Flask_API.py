import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from kafka import KafkaProducer
from pymongo import MongoClient

app = Flask(__name__)

# Kafka
producer = KafkaProducer(
    bootstrap_servers="kafka:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    retries=3,
)
KAFKA_REQUEST_TOPIC = "mydata_prediction_request"

# Mongo
mongo = MongoClient("mongo", 27017)
db = mongo["agile_data_science"]
col_resp = db["mydata_prediction_response"]      # donde escribe Spark
col_req  = db["mydata_prediction_requests"]      # opcional: para ver solicitudes

@app.route("/")
def home():
    # si usas templates: return render_template("form.html")
    return render_template("form.html")

@app.route("/mydata/predict", methods=["POST"])
def mydata_predict():
    # Recoge datos del form (o JSON)
    payload = request.get_json() or request.form.to_dict()

    # Asegura tipos y formato ISO en timestamps si vienen vacíos
    def to_iso(x):
        if not x:
            return datetime.utcnow().isoformat(timespec="seconds")
        return x

    # Genera UUID
    uid = str(uuid.uuid4())
    payload["UUID"] = uid

    # (Opcional) normaliza tipos numéricos si llegan como string:
    ints  = [ "delivery_fee", "commission_fee", "payment_processing_fee"]
    floats = ["order_value", "refunds/chargebacks"]
    for k in ints:
        if k in payload and payload[k] not in (None, ""):
            payload[k] = int(payload[k])
    for k in floats:
        if k in payload and payload[k] not in (None, ""):
            payload[k] = float(payload[k])

    # timestamps
    payload["order_date_and_time"] = to_iso(payload.get("order_date_and_time"))
    

    # Guarda la solicitud (opcional, útil para auditoría)
    try:
        col_req.insert_one({"UUID": uid, "request": payload, "status": "submitted", "ts": datetime.utcnow()})
    except Exception:
        pass

    # Publica en Kafka
    producer.send(KAFKA_REQUEST_TOPIC, payload)
    producer.flush()

    return jsonify({"id": uid, "status": "submitted"})

@app.route("/mydata/predict/response/<uid>", methods=["GET"])
def mydata_predict_response(uid):
    # Busca en la colección donde Spark escribe la predicción
    doc = col_resp.find_one({"UUID": uid}, {"_id": 0})
    if doc:
        # Ejemplo doc: { "UUID": "...", "prediction": 76.12 }
        return jsonify({"id": uid, "status": "done", **doc})
    # Si no hay aún, devolvemos pending (HTTP 202)
    return jsonify({"id": uid, "status": "pending"}), 202

if __name__ == "__main__":
    # Ejecuta Flask en el contenedor agile, expuesto en 5050 (ya mapeado en tu compose)
    app.run(host="0.0.0.0", port=5050, debug=True)