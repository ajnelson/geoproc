#!/bin/bash

outdir="$2"

xmlfile="${outdir/%verify_fiwalk_dfxml.sh/make_fiwalk_dfxml.sh}/fiout.xml"

xmllint "$xmlfile" >/dev/null
