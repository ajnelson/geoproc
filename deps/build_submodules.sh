#!/bin/bash
#install.sh
#
#Configure and install all Git-tracked dependencies for geoproc 

set -e
set -x

case $1 in
  local )
    MAKEINSTALL="make install"
    if [ -z "$2" ]; then
      INSTALLDIR=$HOME/local
    else
      INSTALLDIR=$2
    fi
    ;;
  system )
    MAKEINSTALL="sudo make install"
    INSTALLDIR=/usr/local
    ;;
  * )
    echo "Error: Arguments must be 'local', 'local prefix_dir' or 'system'" >&2
    exit 2
    ;;
esac


REPODIR=`cd $(dirname $(which $0))/..; pwd`

echo "NOTE BEFORE COMPILING:  Ensure you have the necessary path augmentations from ./bashrc"; sleep 2

echo "Note: installing sleuthkit" >&2
pushd $REPODIR/deps/sleuthkit
./bootstrap && ./configure --prefix=$INSTALLDIR && make && $MAKEINSTALL
popd

echo "Note: installing bulk_extractor" >&2
pushd $REPODIR/deps/bulk_extractor
sh bootstrap.sh && ./configure --prefix=$INSTALLDIR && make && $MAKEINSTALL
popd
