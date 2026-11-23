#!/bin/bash
python -m scheduler.main --run-once collect --fetch-all
python -m scheduler.main --run-once analyze
python -m scheduler.main --run-once sync_to_opensearch
python -m scheduler.main --run-once wordcloud
