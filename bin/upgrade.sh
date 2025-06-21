#!/bin/bash

export LOG_FILE="/home/vagrant/upgrade.sh.log"

echo "Removing Spark 2.2.1 ..." | tee -a $LOG_FILE
rm -rf /home/vagrant/spark

echo "Downloading and installing Spark 2.4.4 ..." | tee -a $LOG_FILE
curl -Lko /tmp/spark-2.4.4-bin-without-hadoop.tgz https://archive.apache.org/dist/spark/spark-2.4.4/spark-2.4.4-bin-hadoop2.7.tgz
mkdir -p /home/vagrant/spark
cd /home/vagrant
tar -xvf /tmp/spark-2.4.4-bin-without-hadoop.tgz -C spark --strip-components=1

# Have to set spark.io.compression.codec in Spark local mode
cp /home/vagrant/spark/conf/spark-defaults.conf.template /home/vagrant/spark/conf/spark-defaults.conf
echo 'spark.io.compression.codec org.apache.spark.io.SnappyCompressionCodec' | sudo tee -a /home/vagrant/spark/conf/spark-defaults.conf

# Give Spark 8GB of RAM, use Python3
echo "spark.driver.memory 8g" | sudo tee -a $SPARK_HOME/conf/spark-defaults.conf
echo "spark.executor.cores 2" | sudo tee -a $SPARK_HOME/conf/spark-defaults.conf
echo "PYSPARK_PYTHON=python3" | sudo tee -a $SPARK_HOME/conf/spark-env.sh
echo "PYSPARK_DRIVER_PYTHON=python3" | sudo tee -a $SPARK_HOME/conf/spark-env.sh

# Setup log4j config to reduce logging output
cp $SPARK_HOME/conf/log4j.properties.template $SPARK_HOME/conf/log4j.properties
sed -i 's/INFO/ERROR/g' $SPARK_HOME/conf/log4j.properties

# Give to vagrant
sudo chown -R vagrant /home/vagrant/spark
sudo chgrp -R vagrant /home/vagrant/spark

echo "spark.speculation false" | sudo tee -a /home/vagrant/spark/conf/spark-defaults.conf

echo "spark.jars /home/vagrant/Agile_Data_Code_2/lib/mongo-hadoop-spark-2.0.2.jar,/home/vagrant/Agile_Data_Code_2/lib/mongo-java-driver-3.6.1.jar,/home/vagrant/Agile_Data_Code_2/lib/mongo-hadoop-2.0.2.jar,/home/vagrant/Agile_Data_Code_2/lib/elasticsearch-spark-20_2.11-6.1.2.jar,/home/vagrant/Agile_Data_Code_2/lib/snappy-java-1.1.7.1.jar,/home/vagrant/Agile_Data_Code_2/lib/lzo-hadoop-1.0.5.jar,/home/vagrant/Agile_Data_Code_2/lib/commons-httpclient-3.1.jar" | sudo tee -a /home/vagrant/spark/conf/spark-defaults.conf

