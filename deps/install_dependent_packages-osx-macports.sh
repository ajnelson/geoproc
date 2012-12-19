#!/bin/bash

set -e
set -x

echo "The mysql.connector library is neither installed in OS X, nor packaged by default.  Download from mysql.com (Oracle) and install."

sudo port install \
  graphviz \
  libewf \
  libpst
