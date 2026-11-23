#!/bin/bash
# Run the full data pipeline manually

# 1. Collect Reviews (Fetch All)
echo "Step 1: Collecting Reviews..."
python -m scheduler.main --run-once collect --fetch-all
if [ $? -ne 0 ]; then echo "Collection failed"; exit 1; fi

# 2. Analyze Reviews
echo "Step 2: Analyzing Reviews..."
python -m scheduler.main --run-once analyze
if [ $? -ne 0 ]; then echo "Analysis failed"; exit 1; fi

# 3. Sync to OpenSearch
echo "Step 3: Syncing to OpenSearch..."
python -m scheduler.main --run-once sync_to_opensearch
if [ $? -ne 0 ]; then echo "Sync failed"; exit 1; fi

# 4. Generate Wordcloud
echo "Step 4: Generating Wordcloud..."
python -m scheduler.main --run-once wordcloud
if [ $? -ne 0 ]; then echo "Wordcloud generation failed"; exit 1; fi

echo "Pipeline completed successfully."
