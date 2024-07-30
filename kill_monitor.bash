#!/bin/bash

SCRIPT_NAME="Lunas-Code/startup_and_monitor.bash"
GREP_COUNT=$(ps aux | grep -c $SCRIPT_NAME)

if [ $GREP_COUNT -eq "1" ]; then
    echo "Monitoring script was not found running"
else
    PIDS=$(ps aux | grep $SCRIPT_NAME | awk -v max="$GREP_COUNT" 'NR < max {print $2}')
    for P in $PIDS; do
        kill $P
    done
    echo "Killed $((GREP_COUNT - 1)) Monitoring script process(es)"
fi

PYTHON_NAME="luna_control.py"
GREP_PY_COUNT=$(ps aux | grep -c $PYTHON_NAME)

if [ $GREP_PY_COUNT -eq "1" ]; then
    echo "Python control script was not found running"
else
    PIDS=$(ps aux | grep $PYTHON_NAME | awk -v max="$GREP_PY_COUNT" 'NR < max {print $2}')
    for P in $PIDS; do
        kill $P
    done
    echo "Killed $((GREP_PY_COUNT - 1)) Python script process(es)"
fi
