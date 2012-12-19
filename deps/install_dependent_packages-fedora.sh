#!/bin/bash

set -e
set -x

if [ -r /etc/fedora-release ]; then
  #Assume Fedora
  sudo yum install \
    afflib-devel \
    autoconf \
    automake \
    byacc \
    exiv2 \
    exiv2-devel \
    flex \
    gcc-c++ \
    gettext-devel \
    graphviz \
    java-1.7.0-openjdk-devel \
    libewf-devel \
    libewf-tools \
    libtool \
    libxml2-devel \
    libpst \
    mysql-connector-python \
    mysql-connector-python3 \
    numpy \
    ocaml \
    openssl-devel \
    python-devel \
    python3 \
    python-GeoIP \
    python-matplotlib \
    zlib-devel
fi
