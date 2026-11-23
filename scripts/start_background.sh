#!/bin/bash
python -m flask run --host=0.0.0.0 --port=5952 --reload > logs/flask.log 2>&1 &
