#!/bin/bash
 mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -P"${MYSQL_PORT:-3306}" -h"$MYSQL_HOST"
