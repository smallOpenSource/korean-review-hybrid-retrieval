#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Scheduler Job Status ===${NC}"
echo "Checking for running scheduler jobs..."
echo "----------------------------------------"

# Check for python processes running scheduler jobs
# We exclude the grep process itself and timeout wrapper processes
# Pattern 1: Traditional scheduler.main execution
# Pattern 2: Direct Python execution with AnalyzeReviewsJob
processes=$(ps aux | grep -E "(scheduler\.main|AnalyzeReviewsJob)" | grep -v grep | grep -v " timeout ")

if [ -z "$processes" ]; then
    echo -e "${RED}No scheduler jobs are currently running.${NC}"
else
    echo -e "${GREEN}Found running jobs:${NC}"
    echo ""
    # Print header
    printf "%-10s %-10s %-10s %-50s\n" "PID" "USER" "START" "COMMAND"
    echo "--------------------------------------------------------------------------------"
    
    # Parse and display each process
    echo "$processes" | while read -r line; do
        pid=$(echo $line | awk '{print $2}')
        user=$(echo $line | awk '{print $1}')
        start=$(echo $line | awk '{print $9}')
        # Get the command part (everything after the time)
        # This might vary depending on ps output format, but usually works
        cmd=$(echo $line | awk '{$1=$2=$3=$4=$5=$6=$7=$8=$9=$10=""; print $0}' | sed 's/^[ \t]*//')
        
        # Check for fetch-all flag or all_batches=True parameter
        mode="(NORMAL)"
        if [[ "$cmd" == *"--fetch-all"* ]] || [[ "$cmd" == *"all_batches=True"* ]]; then
            mode="(ALL)"
        fi

        # Try to extract job name from command arguments
        job_name="Unknown"
        if [[ "$cmd" == *"AnalyzeReviewsJob"* ]]; then
            # Direct Python execution batch
            job_name="Batch Analysis ${mode}"
            # Try to extract batch_size if present
            if [[ "$cmd" == *"batch_size="* ]]; then
                batch_size=$(echo "$cmd" | grep -oP 'batch_size=\K[0-9]+')
                job_name="${job_name} (batch=${batch_size})"
            fi
        elif [[ "$cmd" == *"--run-once"* ]]; then
            # Extract word after --run-once
            job_name=$(echo "$cmd" | grep -oP '(?<=--run-once[ =])[^ ]+')
            if [ -z "$job_name" ]; then
                 # Try to see if it's just --run-once without =
                 job_name=$(echo "$cmd" | awk -F'--run-once ' '{print $2}' | awk '{print $1}')
            fi
            job_name="${job_name} ${mode}"
        elif [[ "$cmd" == *"--run-pipeline"* ]]; then
            job_name="Full Pipeline ${mode}"
        else
            job_name="Scheduler Service"
        fi
        
        printf "%-10s %-10s %-10s %-50s\n" "$pid" "$user" "$start" "$job_name"
    done
fi

echo "----------------------------------------"
