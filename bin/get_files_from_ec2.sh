#!/usr/bin/env bash

# Copy all Python code and model files from the EC2 instance to local filessytem
rsync -ruv -e "ssh -i ./agile_data_science.pem" \
    --exclude=cassandra \
    --exclude=data \
    --exclude=janusgraph \
    --exclude=hadoop \
    --exclude=spark \
    --exclude=kafka \
    --exclude=lib \
    --exclude=elasticsearch-hadoop \
    --exclude=elasticsearch \
    --exclude=mongo-hadoop \
    --exclude=mongodb \
    --exclude=tmp \
    --exclude=zeppelin \
    ubuntu@`cat .ec2_hostname`:Agile_Data_Code_2/* .
