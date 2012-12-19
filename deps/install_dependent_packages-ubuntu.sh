#!/bin/bash

set -e
set -x

#python-mysql.connector is only for Python2
echo "Due to a missing Python3 package (mysql.connector), Ubuntu is not currently supported." >&2
exit 1

if [ -r /etc/debian_version ]; then
  #Assume Ubuntu
  sudo apt-get install \
    autoconf \
    exiv2 \
    flex \
    g++ \
    libexiv2-dev \
    libexpat1-dev \
    libtool \
    libxml2-dev \
    libxml2-utils \
    python-mysql.connector \
    ocaml \
    openjdk-7-jdk \
    pst-utils \
    python3 \
    python-dev \
    zlib1g-dev
fi
