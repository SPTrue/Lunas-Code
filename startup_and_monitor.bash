#!/bin/bash

SCRIPT_DIR="$(dirname $0)"

LOG="$SCRIPT_DIR/monitor.log"
touch $LOG

# Limit the log size by discarding old log lines on startup
tail -n5000 $LOG > /tmp/temp.log
cp /tmp/temp.log $LOG
rm /tmp/temp.log

source $SCRIPT_DIR/bin/activate

echo -e "\n\n\e[1m\e[32m$(date)\tStarting Luna Control Monitor script.\n\e[0m" >> $LOG

until python -u $SCRIPT_DIR/luna_control.py >> $LOG 2>> $LOG; do
    echo -e "\n\e[1m\e[33m$(date)\tLuna Controller program has closed. Restarting...\e[0m" >> $LOG
    sleep 1
done
 
echo -e "\n\n\e[1m\e[35m$(date)\tLuna Control Monitor script has exited its monitor loop.\n\e[0m" >> $LOG 
