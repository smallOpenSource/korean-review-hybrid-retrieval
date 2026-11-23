#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Stopping Scheduler Jobs ===${NC}"

# Find python processes running scheduler.main
# We exclude the grep process itself and the current script
pids=$(ps aux | grep "scheduler.main" | grep -v grep | awk '{print $2}')

if [ -z "$pids" ]; then
    echo -e "${GREEN}No scheduler jobs found running.${NC}"
    exit 0
fi

echo -e "Found running jobs with PIDs: ${RED}$pids${NC}"

# Send SIGTERM to all found processes
echo "Sending SIGTERM to processes..."
for pid in $pids; do
    kill $pid 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Sent SIGTERM to PID $pid"
    else
        echo "Failed to send signal to PID $pid (process might be gone)"
    fi
done

# Wait for processes to exit
echo "Waiting for processes to exit..."
sleep 3

# Check if any are still running
remaining_pids=$(ps aux | grep "scheduler.main" | grep -v grep | awk '{print $2}')

if [ -n "$remaining_pids" ]; then
    echo -e "${RED}Some processes are still running: $remaining_pids${NC}"
    echo "Sending SIGKILL (force kill)..."
    for pid in $remaining_pids; do
        kill -9 $pid 2>/dev/null
        echo "Sent SIGKILL to PID $pid"
    done
    
    # Final check
    sleep 1
    final_pids=$(ps aux | grep "scheduler.main" | grep -v grep | awk '{print $2}')
    if [ -n "$final_pids" ]; then
        echo -e "${RED}Failed to kill processes: $final_pids${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}All scheduler jobs have been stopped.${NC}"
