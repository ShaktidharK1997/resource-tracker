# setup_cron.sh
#!/bin/bash
cd $(dirname $0)/..
source .env
/usr/bin/python3 resource_tracker.py >> cron.log 2>&1