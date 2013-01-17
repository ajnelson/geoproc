#!/bin/bash

set -e
set -x

#TODO add mysql.connector check to configure script

if [ -r /etc/debian_version ]; then
  #Assume Ubuntu
  sudo apt-get install \
    autoconf \
    exiv2 \
    flex \
    g++ \
    graphviz \
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
  echo "The mysql.connector library is not packaged for Python 3 in Ubuntu.  Download from mysql.com (Oracle) and install."
fi
