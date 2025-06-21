#!/usr/bin/env bash

scp -i ./agile_data_science.pem bin/download_list.txt ubuntu@$(cat .ec2_hostname):Agile_Data_Code_2/

ssh -i ./agile_data_science.pem ubuntu@$(cat .ec2_hostname) << SSH_COMMANDS

cd Agile_Data_Code_2
tar -cvzf agile_data_science_student_code.tar.gz -T download_list.txt

SSH_COMMANDS

scp -i ./agile_data_science.pem ubuntu@$(cat .ec2_hostname):Agile_Data_Code_2/agile_data_science_student_code.tar.gz ./ads_student_$(cat .ec2_hostname).tar.gz
