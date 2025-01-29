# install_cron.sh
#!/bin/bash
SCRIPT_DIR=$(dirname $(readlink -f $0))
CRON_CMD="*/5 * * * * $SCRIPT_DIR/setup_cron.sh"
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
chmod +x $SCRIPT_DIR/setup_cron.sh
touch $SCRIPT_DIR/cron.log
chmod 644 $SCRIPT_DIR/cron.log