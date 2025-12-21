#!/usr/bin/env bash

kubectl delete namespace spark --ignore-not-found

kubectl delete pv models-pv mongo-pv elastic-pv --ignore-not-found
rm -rf models/gbt models/checkpoints data models/jars models/.ivy2* models/.pylibs