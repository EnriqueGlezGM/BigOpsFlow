from flask import Flask, request, jsonify, render_template
from kafka import KafkaProducer
import json
import uuid
import pymongo
import time

app = Flask(__name__)

# Kafka producer
producer = KafkaProducer(
    bootstrap_servers='kafka:9092',
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

# Mongo client
mongo_client = pymongo.MongoClient("mongo")
mongo_db = mongo_client.agile_data_science
mongo_collection = mongo_db.mydata_prediction_response

@app.route("/")
def index():
    return render_template("my_form.html")

@app.route("/mydata/predict", methods=["POST"])
def predict():
    data = dict(request.form)
    data["UUID"] = str(uuid.uuid4())

    print("📥 Recibido formulario:", data)

    try:
        data["order_value"] = float(data["order_value"])
        data["refunds/chargebacks"] = float(data["refunds/chargebacks"])
    except Exception as e:
        print("❌ Error al convertir tipos:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

    try:
        data["order_id"] = int(data["order_id"])
        data["delivery_fee"] = float(data["delivery_fee"])
        data["commission_fee"] = float(data["commission_fee"])
        data["payment_processing_fee"] = float(data["payment_processing_fee"])
        data["order_date_and_time"] = data["order_date_and_time"] + ":00"
        data["delivery_date_and_time"] = data["delivery_date_and_time"] + ":00"
    except Exception as e:
        print("❌ Error al convertir tipos:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

    print("📤 Enviando a Kafka:", data)

    producer.send("mydata_prediction_request", value=data)

    return jsonify({"status": "submitted", "id": data["UUID"]})

@app.route("/mydata/predict/response/<id>", methods=["GET"])
def get_response(id):
    prediction = mongo_collection.find_one({"UUID": id})
    if prediction:
        prediction.pop("_id", None)
        return jsonify(prediction)
    else:
        return jsonify({"status": "pending"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)