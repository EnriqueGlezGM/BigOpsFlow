# This code sample is meant to be executed line-by-line in a 
# pyspark session.
#
# Prior to launching pyspark, run the following line in the 
# shell where pyspark will be launched.
#
# export PYSPARK_DRIVER_PYTHON=ipython
#
# The pyspark launch command needs to have additional command line
# arguments passed to ensure that Java classes used to connect to
# MongoDB are found.
#
# The Java classes reside in JAR files that were
# preinstalled via the boostrap.sh script and placed in the 
# lib directory. You will need to note the version of the
# libraries by inspecting the JAR filenames.  For example,
# if running the following shell command:
#
# $ ls Agile_Data_Code_2/lib/mongo*.jar
#
# yields the following listing:
#
# Agile_Data_Code_2/lib/mongo-hadoop-2.0.2.jar	    
# Agile_Data_Code_2/lib/mongo-hadoop-spark-2.0.2.jar
# Agile_Data_Code_2/lib/mongo-java-driver-3.6.1.jar
#
# then the mongo-hadoop version would be 2.0.2, and the 
# Mongo-Java version would be 3.6.1.
#
# Choosing to set these versions as environment variables
# will make the invocation of the command much less error
# prone.
#
# MONGOHADOOP_VERSION=2.0.2
# MONGOJAVA_VERSION=3.6.1
#
# The names of the JAR files can then be pieced together
# from the version strings.
#
# MONGOHADOOPSPARK_JAR=./lib/mongo-hadoop-spark-$MONGOHADOOP_VERSION.jar
# MONGOJAVADRIVER_JAR=./lib/mongo-java-driver-$MONGOJAVA_VERSION.jar
# MONGOHADOOP_JAR=./lib/mongo-hadoop-$MONGOHADOOP_VERSION.jar 
#
# You can then launch the pyspark session using the following
# shell command from the Agile_Data_Code_2 directory:
#
# pyspark \
#   --jars $MONGOHADOOPSPARK_JAR,$MONGOJAVADRIVER_JAR,$MONGOHADOOP_JAR \
#   --driver-class-path $MONGOHADOOPSPARK_JAR:$MONGOJAVADRIVER_JAR:$MONGOHADOOP_JAR

import pymongo_spark
# Important: activate pymongo_spark.
pymongo_spark.activate()

csv_lines = sc.textFile("data/example.csv")
data = csv_lines.map(lambda line: line.split(","))
schema_data = data.map(lambda x: {'name': x[0], 'company': x[1], 'title': x[2]})
schema_data.saveToMongoDB('mongodb://localhost:27017/agile_data_science.executives')

