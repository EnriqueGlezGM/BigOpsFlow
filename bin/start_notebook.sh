#!/bin/bash

cd $PROJECT_HOME

# Stop all existing jupyter notebooks
ps aux | grep -i jupyter | grep -v grep | tr -s ' ' | cut -d ' ' -f2 | xargs -I {} sudo kill -9 {}

# Start a new Jupyter Notebook
nohup jupyter notebook --ip=0.0.0.0 --NotebookApp.token= --allow-root --no-browser &

echo "Jupyter notebook started!"
