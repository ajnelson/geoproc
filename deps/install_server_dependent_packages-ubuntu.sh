#!/bin/bash

set -e
set -x

#python-mysql.connector is only for Python2
echo "Due to a missing Python3 package (mysql.connector), Ubuntu is not currently supported." >&2
exit 1

if [ -r /etc/debian_version ]; then
  #Assume Ubuntu
  sudo apt-get install \
    mysql-server
fi
