#!/usr/bin/env bash

ps aux| grep jupyter | grep -v grep | tr -s ' '| cut -d ' ' -f2 | xargs -I {} kill -9 {}

echo "Killed Jupyter Notebook!"
