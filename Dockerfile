ARG OWNER=jupyter
ARG BASE_CONTAINER=$OWNER/pyspark-notebook:spark-3.2.0
FROM $BASE_CONTAINER

LABEL maintainer="Russell Jurney <russell.jurney@gmail.com>"

# Fix DL4006
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# Install the MongoDB Client CLI
RUN apt-get update --yes && \
    sudo apt-get install -y iputils-ping gnupg curl jq && \
    wget -qO - https://www.mongodb.org/static/pgp/server-5.0.asc | sudo apt-key add - && \
    echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/5.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-5.0.list && \
    sudo apt-get update && \
    sudo apt-get install -y mongodb-mongosh mongodb-org-tools && \
    echo "mongodb-mongosh hold" | sudo dpkg --set-selections && \
    echo "mongodb-org-tools hold" | sudo dpkg --set-selections && \
    apt-get clean

RUN pip install poetry

COPY pyproject.toml /home/jovyan/pyproject.toml
COPY poetry.lock /home/jovyan/poetry.lock
COPY requirements.txt /home/jovyan/requirements.txt

RUN poetry install && pip install -r requirements.txt
