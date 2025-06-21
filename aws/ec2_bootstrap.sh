#!/bin/bash

# Update and install critical packages
LOG_FILE="/home/ubuntu/ec2_bootstrap.sh.log"
touch $LOG_FILE
echo "Logging to \"$LOG_FILE\" ..."

echo "Installing essential packages via apt-get in non-interactive mode ..." | tee -a $LOG_FILE
sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::options::="--force-confdef" -o DPkg::options::="--force-confold" upgrade
sudo apt-get install -y zip unzip curl bzip2 python-dev build-essential git libssl1.0.0 libssl-dev \
    software-properties-common debconf-utils apt-transport-https

# Update the motd message to warn incompleteness
echo "Updating motd boot message to warn setup incomplete ..." | tee -a $LOG_FILE
sudo apt-get install -y update-motd
cat > /home/ubuntu/agile_data_science.message << END_HELLO

------------------------------------------------------------------------------------------------------------------------

This system is not yet done loading! It will not work yet. Come back in a few minutes. This can take as long as 20 minutes because there are large files to download.

END_HELLO

cat <<EOF | sudo tee /etc/update-motd.d/99-agile-data-science
#!/bin/bash

cat /home/ubuntu/agile_data_science.message
EOF
sudo chmod 0755 /etc/update-motd.d/99-agile-data-science
sudo update-motd

# Intall OpenJDK 8 - Oracle Java no longer available
sudo add-apt-repository -y ppa:openjdk-r/ppa
sudo apt-get update
sudo apt-get install -y openjdk-8-jdk

export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
echo "export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64" | sudo tee -a /home/ubuntu/.bash_profile

# Install Miniconda
echo "Installing and configuring miniconda3 latest ..." | tee -a $LOG_FILE
curl -Lko /tmp/Miniconda3-latest-Linux-x86_64.sh https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x /tmp/Miniconda3-latest-Linux-x86_64.sh
/tmp/Miniconda3-latest-Linux-x86_64.sh -b -p /home/ubuntu/anaconda

export PATH=/home/ubuntu/anaconda/bin:$PATH # setup .bash_profile at end

sudo chown -R ubuntu:ubuntu /home/ubuntu/anaconda

# Clone repo, install Python dependencies
echo "Cloning https://github.com/rjurney/Agile_Data_Code_2 repository and installing dependencies ..." \
  | tee -a $LOG_FILE
cd /home/ubuntu
git clone https://github.com/rjurney/Agile_Data_Code_2
cd /home/ubuntu/Agile_Data_Code_2
export PROJECT_HOME=/home/ubuntu/Agile_Data_Code_2
echo "export PROJECT_HOME=/home/ubuntu/Agile_Data_Code_2" | sudo tee -a /home/ubuntu/.bash_profile
conda install -y python=3.5
conda update -y -n base conda
conda install -y tornado=4.5.3 # To deal with https://github.com/jupyter/notebook/issues/3544
conda install -y iso8601 numpy scipy scikit-learn matplotlib ipython jupyter
pip install --upgrade pip
pip install -r requirements.txt
sudo chown -R ubuntu:ubuntu /home/ubuntu/Agile_Data_Code_2
cd /home/ubuntu

# Install commons-httpclient
curl -Lko /home/ubuntu/Agile_Data_Code_2/lib/commons-httpclient-3.1.jar http://central.maven.org/maven2/commons-httpclient/commons-httpclient/3.1/commons-httpclient-3.1.jar

# Install Hadoop
echo "" | tee -a $LOG_FILE
echo "Downloading and installing Hadoop 3.0.1 ..." | tee -a $LOG_FILE
curl -Lko /tmp/hadoop-3.0.1.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-3.0.1/hadoop-3.0.1.tar.gz
mkdir -p /home/ubuntu/hadoop
cd /home/ubuntu/
tar -xvf /tmp/hadoop-3.0.1.tar.gz -C hadoop --strip-components=1

echo "Configuring Hadoop 3.0.1 ..." | tee -a $LOG_FILE
echo "" >> /home/ubuntu/.bash_profile
echo '# Hadoop environment setup' | sudo tee -a /home/ubuntu/.bash_profile
export HADOOP_HOME=/home/ubuntu/hadoop
echo 'export HADOOP_HOME=/home/ubuntu/hadoop' | sudo tee -a /home/ubuntu/.bash_profile
export PATH=$PATH:$HADOOP_HOME/bin
echo 'export PATH=$PATH:$HADOOP_HOME/bin' | sudo tee -a /home/ubuntu/.bash_profile
export HADOOP_CLASSPATH=$(hadoop classpath)
echo 'export HADOOP_CLASSPATH=$(hadoop classpath)' | sudo tee -a /home/ubuntu/.bash_profile
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
echo 'export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop' | sudo tee -a /home/ubuntu/.bash_profile

# Give to ubuntu
echo "Giving hadoop to user ubuntu ..." | tee -a $LOG_FILE
sudo chown -R ubuntu:ubuntu /home/ubuntu/hadoop

# Install Spark
echo "" | tee -a $LOG_FILE
echo "Downloading and installing Spark 2.4.2 ..." | tee -a $LOG_FILE
curl -Lko /tmp/spark-2.4.2-bin-hadoop2.7.tgz http://archive.apache.org/dist/spark/spark-2.4.2/spark-2.4.2-bin-hadoop2.7.tgz
mkdir -p /home/ubuntu/spark
cd /home/ubuntu
tar -xvf /tmp/spark-2.4.2-bin-hadoop2.7.tgz -C spark --strip-components=1
cd spark/python

echo "Configuring Spark 2.4.2 ..." | tee -a $LOG_FILE
echo "" >> /home/ubuntu/.bash_profile
echo "# Spark environment setup" | sudo tee -a /home/ubuntu/.bash_profile
export SPARK_HOME=/home/ubuntu/spark
echo 'export SPARK_HOME=/home/ubuntu/spark' | sudo tee -a /home/ubuntu/.bash_profile
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop/
echo 'export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop/' | sudo tee -a /home/ubuntu/.bash_profile
export SPARK_DIST_CLASSPATH=`$HADOOP_HOME/bin/hadoop classpath`
echo 'export SPARK_DIST_CLASSPATH=`$HADOOP_HOME/bin/hadoop classpath`' | sudo tee -a /home/ubuntu/.bash_profile
export PATH=$PATH:$SPARK_HOME/bin
echo 'export PATH=$PATH:$SPARK_HOME/bin' | sudo tee -a /home/ubuntu/.bash_profile

# Have to set spark.io.compression.codec in Spark local mode
cp /home/ubuntu/spark/conf/spark-defaults.conf.template /home/ubuntu/spark/conf/spark-defaults.conf
echo 'spark.io.compression.codec org.apache.spark.io.SnappyCompressionCodec' | sudo tee -a /home/ubuntu/spark/conf/spark-defaults.conf

# Configure Spark for an r5.xlarge with Python3
echo "spark.driver.memory 25g" | sudo tee -a $SPARK_HOME/conf/spark-defaults.conf
echo "spark.executor.cores 4" | sudo tee -a $SPARK_HOME/conf/spark-defaults.conf
echo "PYSPARK_PYTHON=python3" | sudo tee -a $SPARK_HOME/conf/spark-env.sh
echo "PYSPARK_DRIVER_PYTHON=python3" | sudo tee -a $SPARK_HOME/conf/spark-env.sh

# Setup log4j config to reduce logging
cp $SPARK_HOME/conf/log4j.properties.template $SPARK_HOME/conf/log4j.properties
sed -i 's/INFO/ERROR/g' $SPARK_HOME/conf/log4j.properties

# Give to ubuntu
echo "Giving spark to user ubuntu ..." | tee -a $LOG_FILE
sudo chown -R ubuntu:ubuntu /home/ubuntu/spark

# Install MongoDB and deps
echo "" | tee -a $LOG_FILE
echo "Installing MongoDB via apt-get ..." | tee -a $LOG_FILE
sudo apt-get install -y mongodb
sudo mkdir -p /data/db
sudo chown -R mongodb:mongodb /data/db

# run MongoDB as daemon
echo "Running MongoDB as a daemon ..." | tee -a $LOG_FILE
sudo systemctl start mongodb

# Get the MongoDB Java Driver
echo "Fetching the MongoDB Java driver ..." | tee -a $LOG_FILE
curl -Lko /home/ubuntu/Agile_Data_Code_2/lib/mongo-java-driver-3.4.2.jar http://central.maven.org/maven2/org/mongodb/mongo-java-driver/3.4.2/mongo-java-driver-3.4.2.jar

# Install the mongo-hadoop project
echo "" | tee -a $LOG_FILE
echo "Downloading and installing the mongo-hadoop project version 2.0.2 ..." | tee -a $LOG_FILE
curl -Lko /tmp/mongo-hadoop-r2.0.2.tar.gz https://github.com/mongodb/mongo-hadoop/archive/r2.0.2.tar.gz
mkdir /home/ubuntu/mongo-hadoop
cd /home/ubuntu
tar -xvzf /tmp/mongo-hadoop-r2.0.2.tar.gz -C mongo-hadoop --strip-components=1
rm -rf /tmp/mongo-hadoop-r2.0.2.tar.gz

# Now build the mongo-hadoop-spark jars
echo "Building mongo-hadoop-spark jars ..." | tee -a $LOG_FILE
cd /home/ubuntu/mongo-hadoop
./gradlew jar
cp /home/ubuntu/mongo-hadoop/spark/build/libs/mongo-hadoop-spark-*.jar /home/ubuntu/Agile_Data_Code_2/lib/
cp /home/ubuntu/mongo-hadoop/build/libs/mongo-hadoop-*.jar /home/ubuntu/Agile_Data_Code_2/lib/
cd /home/ubuntu

# Now build the pymongo_spark package
echo "Building the pymongo_spark package ..." | tee -a $LOG_FILE
cd /home/ubuntu/mongo-hadoop/spark/src/main/python
python setup.py install
cp /home/ubuntu/mongo-hadoop/spark/src/main/python/pymongo_spark.py /home/ubuntu/Agile_Data_Code_2/lib/
export PYTHONPATH=$PYTHONPATH:$PROJECT_HOME/lib
echo "" | sudo tee -a /home/ubuntu/.bash_profile
echo 'export PYTHONPATH=$PYTHONPATH:$PROJECT_HOME/lib' | sudo tee -a /home/ubuntu/.bash_profile
cd /home/ubuntu

echo "Nuking the source to mongo-hadoop ..." | tee -a $LOG_FILE
rm -rf /home/ubuntu/mongo-hadoop

# Install ElasticSearch and the Elasticsearch for Hadoop package
echo "curl -sLko /tmp/elasticsearch-5.6.0.tar.gz https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-5.6.0.tar.gz"
curl -sLko /tmp/elasticsearch-5.6.0.tar.gz https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-5.6.0.tar.gz
mkdir /home/ubuntu/elasticsearch
cd /home/ubuntu
tar -xvzf /tmp/elasticsearch-5.6.0.tar.gz -C elasticsearch --strip-components=1
sudo chown -R ubuntu:ubuntu /home/ubuntu/elasticsearch
sudo mkdir -p /home/ubuntu/elasticsearch/logs
sudo chown -R ubuntu:ubuntu /home/ubuntu/elasticsearch/logs

# Run elasticsearch
sudo -u ubuntu /home/ubuntu/elasticsearch/bin/elasticsearch -d

# Run a query to test - should return error json
echo "Testing Elasticsearch with a query ..." | tee -a $LOG_FILE
curl 'http://localhost:9200/agile_data_science/on_time_performance/_search?q=Origin:ATL&pretty' | tee -a $LOG_FILE

# Install Elasticsearch for Hadoop
echo "" | tee -a $LOG_FILE
echo "Installing and configuring Elasticsearch for Hadoop/Spark version 5.5.1 ..." | tee -a $LOG_FILE
curl -Lko /tmp/elasticsearch-hadoop-6.1.3.zip http://download.elastic.co/hadoop/elasticsearch-hadoop-6.1.3.zip
unzip /tmp/elasticsearch-hadoop-6.1.3.zip
mv /home/ubuntu/elasticsearch-hadoop-6.1.3 /home/ubuntu/elasticsearch-hadoop
cp /home/ubuntu/elasticsearch-hadoop/dist/elasticsearch-hadoop-6.1.3.jar /home/ubuntu/Agile_Data_Code_2/lib/
cp /home/ubuntu/elasticsearch-hadoop/dist/elasticsearch-spark-20_2.11-6.1.3.jar /home/ubuntu/Agile_Data_Code_2/lib/
echo "spark.speculation false" | sudo tee -a /home/ubuntu/spark/conf/spark-defaults.conf
rm -f /tmp/elasticsearch-hadoop-6.1.3.zip
rm -rf /home/ubuntu/elasticsearch-hadoop/conf/spark-defaults.conf

sudo chown -R ubuntu:ubuntu /home/ubuntu/elasticsearch-hadoop

# Install and add snappy-java and lzo-java to our classpath below via spark.jars
cd /home/ubuntu/Agile_Data_Code_2
curl -Lko lib/snappy-java-1.1.7.1.jar http://central.maven.org/maven2/org/xerial/snappy/snappy-java/1.1.7.1/snappy-java-1.1.7.1.jar
curl -Lko lib/lzo-hadoop-1.0.5.jar http://central.maven.org/maven2/org/anarres/lzo/lzo-hadoop/1.0.5/lzo-hadoop-1.0.5.jar
cd /home/ubuntu

# Set the spark.jars path
echo "spark.jars /home/ubuntu/Agile_Data_Code_2/lib/mongo-hadoop-spark-2.0.2.jar,/home/ubuntu/Agile_Data_Code_2/lib/mongo-java-driver-3.4.2.jar,/home/ubuntu/Agile_Data_Code_2/lib/mongo-hadoop-2.0.2.jar,/home/ubuntu/Agile_Data_Code_2/lib/elasticsearch-hadoop-6.1.3.jar,/home/ubuntu/Agile_Data_Code_2/lib/elasticsearch-spark-20_2.10-6.1.3.jar,/home/ubuntu/Agile_Data_Code_2/lib/snappy-java-1.1.7.1.jar,/home/ubuntu/Agile_Data_Code_2/lib/lzo-hadoop-1.0.5.jar,/home/ubuntu/Agile_Data_Code_2/lib/commons-httpclient-3.1.jar" | sudo tee -a /home/ubuntu/spark/conf/spark-defaults.conf

# Kafka install and setup
echo "" | tee -a $LOG_FILE
echo "Downloading and installing Kafka version 2.1.1 for Scala 2.11 ..." | tee -a $LOG_FILE
curl -Lko /tmp/kafka_2.11-2.1.1.tgz https://www-us.apache.org/dist/kafka/2.1.1/kafka_2.11-2.1.1.tgz
mkdir -p /home/ubuntu/kafka
cd /home/ubuntu/
tar -xvzf /tmp/kafka_2.11-2.1.1.tgz -C kafka --strip-components=1 && rm -f /tmp/kafka_2.11-2.1.1.tgz

# Give to ubuntu
echo "Giving Kafka to user ubuntu ..." | tee -a $LOG_FILE
sudo chown -R ubuntu:ubuntu /home/ubuntu/kafka

# Set the log dir to kafka/logs
echo "Configuring logging for kafka to go into kafka/logs directory ..." | tee -a $LOG_FILE
sed -i '/log.dirs=\/tmp\/kafka-logs/c\log.dirs=logs' /home/ubuntu/kafka/config/server.properties

# Run zookeeper, then Kafka
echo "Running Zookeeper as a daemon ..." | tee -a $LOG_FILE
sudo -H -u ubuntu /home/ubuntu/kafka/bin/zookeeper-server-start.sh -daemon /home/ubuntu/kafka/config/zookeeper.properties
echo "Running Kafka Server as a daemon ..." | tee -a $LOG_FILE
sudo -H -u ubuntu /home/ubuntu/kafka/bin/kafka-server-start.sh -daemon /home/ubuntu/kafka/config/server.properties

# Install and setup Airflow
echo "" | tee -a $LOG_FILE
echo "Installing Airflow via pip ..." | tee -a $LOG_FILE
pip install airflow[hive]
mkdir /home/ubuntu/airflow
mkdir /home/ubuntu/airflow/dags
mkdir /home/ubuntu/airflow/logs
mkdir /home/ubuntu/airflow/plugins

echo "Giving airflow directory to user ubuntu ..." | tee -a $LOG_FILE
sudo chown -R ubuntu:ubuntu /home/ubuntu/airflow

airflow initdb
airflow webserver -D &
airflow scheduler -D &

echo "Giving airflow directory to user ubuntu yet again and putting same in .bash_profile ..." | tee -a $LOG_FILE
sudo chown -R ubuntu:ubuntu /home/ubuntu/airflow
echo "sudo chown -R ubuntu:ubuntu /home/ubuntu/airflow" | sudo tee -a /home/ubuntu/.bash_profile

# Jupyter server setup
echo "" | tee -a $LOG_FILE
echo "Starting Jupyter notebook server ..." | tee -a $LOG_FILE
jupyter-notebook --generate-config
cp /home/ubuntu/Agile_Data_Code_2/jupyter_notebook_config.py /home/ubuntu/.jupyter/

mkdir /home/ubuntu/certs
sudo openssl req -x509 -nodes -days 365 -newkey rsa:1024 -subj "/C=US" -keyout /home/ubuntu/certs/mycert.pem -out /home/ubuntu/certs/mycert.pem

cd /home/ubuntu/Agile_Data_Code_2
jupyter notebook --ip=0.0.0.0 --NotebookApp.token= --allow-root --no-browser &
cd

# Install Ant
sudo apt-get install -y ant

# Install Cassandra from source as the latest 3.11.1 build is broken...
echo "" | tee -a $LOG_FILE
echo "Installing Cassandra ..."
git clone https://github.com/apache/cassandra
cd cassandra
git checkout cassandra-3.11
ant
bin/cassandra
export PATH=$PATH:/home/ubuntu/cassandra/bin
echo 'export PATH=$PATH:/home/ubuntu/cassandra/bin' | sudo tee -a /home/ubuntu/.bash_profile
cd ..

# Install and setup JanusGraph
echo "" | tee -a $LOG_FILE
echo "Installing JanusGraph ..." | tee -a $LOG_FILE
cd
curl -Lko /tmp/janusgraph-0.2.0-hadoop2.zip \
  https://github.com/JanusGraph/janusgraph/releases/download/v0.2.0/janusgraph-0.2.0-hadoop2.zip
unzip -d . /tmp/janusgraph-0.2.0-hadoop2.zip
mv janusgraph-0.2.0-hadoop2 janusgraph
rm /tmp/janusgraph-0.2.0-hadoop2.zip

# Download data
cd /home/ubuntu/Agile_Data_Code_2
./download.sh

# Install phantomjs
/home/ubuntu/Agile_Data_Code/install/phantomjs.sh

# Install jq
bash ./jq_install.sh

# Pretty
echo 'alias ls="ls --color=auto"' | sudo tee -a /home/ubuntu/.bash_profile

# Use Anaconda Python
export PATH=/home/ubuntu/anaconda/bin:$PATH
echo 'export PATH=/home/ubuntu/anaconda/bin:$PATH' | sudo tee -a /home/ubuntu/.bash_profile

# make sure we own ~/.bash_profile after lots of 'sudo tee'
sudo chown ubuntu:ubuntu ~/.bash_profile

# Update the motd message to create instructions for ssh users
echo "Updating motd boot message with instructions for the user of the image ..." | tee -a $LOG_FILE
sudo apt-get install -y update-motd
cat > /home/ubuntu/agile_data_science.message << END_HELLO

----------------------------------------------------------------------------------------------------------------------
Welcome to Agile Data Science 2.0!

If the Agile_Data_Code_2 directory (and others for hadoop, spark, mongodb, elasticsearch, etc.) aren't present, please wait for the install script to finish.

The data has already been downloaded but if you need to do so:

cd Agile_Data_Code_2
./download.sh

Note: to run the web applications and view them at http://localhost:5000 you will now need to run the ec2_create_tunnel.sh script from your local machine.

If you have problems, please file an issue at https://github.com/rjurney/Agile_Data_Code_2/issues
------------------------------------------------------------------------------------------------------------------------

For help building 'big data' applications like this one, or for training regarding same, contact Russell Jurney <rjurney@datasyndrome.com> or at http://datasyndrome.com

Enjoy! Russell Jurney @rjurney <russell.jurney@gmail.com> http://linkedin.com/in/russelljurney

END_HELLO

cat <<EOF | sudo tee /etc/update-motd.d/99-agile-data-science
#!/bin/bash

cat /home/ubuntu/agile_data_science.message
EOF
sudo chmod 0755 /etc/update-motd.d/99-agile-data-science
sudo update-motd

# Cleanup
echo "Cleaning up ..." | tee -a $LOG_FILE
sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
