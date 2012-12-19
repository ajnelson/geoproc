#!/bin/bash

set -e

#Check out some of the submodules that are tracking Python scripts
if [ -d .git -a ! -d deps/bulk_extractor/python ]; then
  git submodule init deps/bulk_extractor
  git submodule update deps/bulk_extractor
fi

if [ -d .git -a ! -d deps/dfxml/python ]; then
  git submodule init deps/dfxml
  git submodule update deps/dfxml
fi

aclocal
automake --add-missing
autoreconf
