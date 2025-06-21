#!/bin/bash

ps aux|grep -i flask|tr -s ' '|cut -d ' ' -f2|xargs kill -9
sudo netstat -ap|grep 5000|tr -s ' '|cut -d ' ' -f7|cut -d '/' -f1|xargs sudo kill -9
