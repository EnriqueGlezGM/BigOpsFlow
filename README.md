```
git clone https://github.com/EnriqueGlezGM/BigOpsFlow.git
cd BigOpsFlow
resources/download_data.sh
python3 -m venv env
source activate
pip install --upgrade pip
pip install -r requirements.txt
tar -xzf kafka_2.12-3.4.0.tgz
tar -xzf apache-zookeeper-3.8.4-bin.tar.gz
tar -xzf spark-3.3.3-bin-hadoop3.tgz
cd kafka_2.12-3.4.0
bin/zookeeper-server-start.sh config/zookeeper.properties
````

en otro terminal:
````
python3 -m venv env
source activate
cd kafka_2.12-3.4.0
bin/kafka-server-start.sh config/server.properties
````

En otro terminal:
````
python3 -m venv env
source activate
cd kafka_2.12-3.4.0
bin/kafka-topics.sh \
--delete \
--bootstrap-server localhost:9092 \
--topic flight_delay_classification_request
bin/kafka-topics.sh \
--create \
--bootstrap-server localhost:9092 \
--replication-factor 1 \
--partitions 1 \
--topic flight_delay_classification_request
````

You should see the following message:
````
WARNING: Due to limitations in metric names, topics with a period ('.') or underscore ('_') could collide. To avoid issues it is best to use either, but not both.
Created topic flight_delay_classification_request.
````
You can see the topic we created with the list topics command:
````
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
````
Output:
````
flight_delay_classification_request
````
````
bin/kafka-console-consumer.sh \
--bootstrap-server localhost:9092 \
--topic flight_delay_classification_request \
--from-beginning
````

En otro terminal:
````
python3 -m venv env
source activate
brew services
````
Output:
````
Name                  Status  User File
mongodb-community@6.0 started root ~/Library/LaunchAgents/homebrew.mxcl.mongodb-community@6.0.plist     
````
Run the import_distances.sh script
````
./resources/import_distances.sh
````
Output:
````
2024-10-23T17:52:52.499+0200	connected to: mongodb://localhost/
2024-10-23T17:52:52.583+0200	4696 document(s) imported successfully. 0 document(s) failed to import.
MongoDB shell version v5.0.29
connecting to: mongodb://127.0.0.1:27017/agile_data_science?compressors=disabled&gssapiServiceName=mongodb
Implicit session: session { "id" : UUID("a5570392-70fb-4095-ab27-96d5b78d31e1") }
MongoDB server version: 6.0.18
WARNING: shell and server versions do not match
{
	"numIndexesBefore" : 1,
	"numIndexesAfter" : 2,
	"createdCollectionAutomatically" : false,
	"ok" : 1
}
````
Si dice "all indexes already exist" habra que:
````
mongo
use agile_data_science
db.dropDatabase()
show collections
````
## Train and Save de the model with PySpark mllib
````
python3 resources/train_spark_mllib_model.py .
ls models
cd $PROJECT_HOME/flight_prediction/
sbt clean package
cd $PROJECT_HOME
spark-submit \
--class es.upm.dit.ging.predictor.MakePrediction \
--master "local[*]" \
--packages org.mongodb.spark:mongo-spark-connector_2.12:10.1.1,org.apache.spark:spark-sql-kafka-0-10_2.12:3.3.0 \
flight_prediction/target/scala-2.12/flight_prediction_2.12-0.1.jar
````

En otro terminal

````
python3 -m venv env
source activate
python3 resources/web/predict_flask.py
````

````
lsof -i :5001
kill -9 <PID>
````
Output:

````
* Serving Flask app 'predict_flask'
* Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
* Running on all addresses (0.0.0.0)
* Running on http://127.0.0.1:5001
* Running on http://192.168.1.55:5001
Press CTRL+C to quit
* Restarting with watchdog (fsevents)
* Debugger is active!
````
Now, visit http://127.0.0.1:5001/flights/delays/predict_kafka and, for fun, open the JavaScript console. Enter a nonzero departure delay, an ISO-formatted date (I used 2016-12-25, which was in the future at the time I was writing this), a valid carrier code (use AA or DL if you don’t know one), an origin and destination (my favorite is ATL → SFO), and a valid flight number (e.g., 1519), and hit Submit. Watch the debug output in the JavaScript console as the client polls for data from the response endpoint at /flights/delays/predict/classify_realtime/response/.

Quickly switch windows to your Spark console. Within 10 seconds, the length we’ve configured of a minibatch, you should see something like the following:

## Check the predictions records inserted in MongoDB
````
mongo
show dbs
use agile_data_science;
db.flight_delay_classification_response.find();

````
You must have a similar output as:

````
{ "_id" : ObjectId("5d8dcb105e8b5622696d6f2e"), "Origin" : "ATL", "DayOfWeek" : 6, "DayOfYear" : 360, "DayOfMonth" : 25, "Dest" : "SFO", "DepDelay" : 290, "Timestamp" : ISODate("2019-09-27T08:40:48.175Z"), "FlightDate" : ISODate("2016-12-24T23:00:00Z"), "Carrier" : "AA", "UUID" : "8e90da7e-63f5-45f9-8f3d-7d948120e5a2", "Distance" : 2139, "Route" : "ATL-SFO", "Prediction" : 3 }
{ "_id" : ObjectId("5d8dcba85e8b562d1d0f9cb8"), "Origin" : "ATL", "DayOfWeek" : 6, "DayOfYear" : 360, "DayOfMonth" : 25, "Dest" : "SFO", "DepDelay" : 291, "Timestamp" : ISODate("2019-09-27T08:43:20.222Z"), "FlightDate" : ISODate("2016-12-24T23:00:00Z"), "Carrier" : "AA", "UUID" : "d3e44ea5-d42c-4874-b5f7-e8a62b006176", "Distance" : 2139, "Route" : "ATL-SFO", "Prediction" : 3 }
{ "_id" : ObjectId("5d8dcbe05e8b562d1d0f9cba"), "Origin" : "ATL", "DayOfWeek" : 6, "DayOfYear" : 360, "DayOfMonth" : 25, "Dest" : "SFO", "DepDelay" : 5, "Timestamp" : ISODate("2019-09-27T08:44:16.432Z"), "FlightDate" : ISODate("2016-12-24T23:00:00Z"), "Carrier" : "AA", "UUID" : "a153dfb1-172d-4232-819c-8f3687af8600", "Distance" : 2139, "Route" : "ATL-SFO", "Prediction" : 1 }


````

