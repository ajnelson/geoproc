#!/usr/bin/env python3
#-*- coding: iso-8859-1 -*-

__version__ = "0.3.3"

import getopt, sys
import xml.dom.minidom
import fractions
import mysql.connector
import os
import re
import argparse
import sqlite3
import copy
import traceback
import math

import geoproc_cfg
import geoproc_library

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

SQL_CREATE_EXIF_HEADERS_VOTES = """CREATE TABLE exif_headers_votes (
  forensic_path TEXT,
  fiwalk_id NUMBER,
  fs_obj_id NUMBER,
  obj_id NUMBER,
  file_in_web_cache BOOLEAN,
  believed_timestamp TEXT,
  exif_datetime TEXT,
  exif_datestamp TEXT,
  exif_gps_lon NUMBER,
  exif_gps_lat NUMBER,
  exif_gps_datestamp TEXT,
  exif_gps_timestamp TEXT,
  city TEXT,
  region TEXT,
  country TEXT,
  postalCode TEXT,
  distance_miles TEXT,
  database_queried BOOLEAN
);"""

def dms_to_decimal(data):
    retval = 0
    val = []
    for element in data.split(b' '):
        nd = element.split(b'/')
        if len(nd) != 2:
           sys.stderr.write("Unexpected data format (no numerator-denominator pairing): %r, element %r\n" % (data, element))
           return None
        numerator, denominator = nd
        if int(denominator) == 0 or float(denominator) == 0.0:
            sys.stderr.write("Warning: Data would cause division by 0: %r. Skipped.\n" % data)
            return None
        val.append('%f' % (float(numerator)/float(denominator)))
    if len(val) != 3:
        sys.stderr.write("Warning: Unexpected data (expected three components): %r.  Proceeding with less-precise calculation.\n" % data)
    for (i,v) in enumerate(val):
        retval += float(v) / (60**i)
    return retval

def hms_fraction_to_decimal(data):
  val = ['%.2d' % (int(numerator)/int(denominator)) for numerator, denominator in [element.split(b'/') for element in data.split(b' ')]]
  return (val[0] + ":" + val[1] + ":" + val[2])

def main():
    global args
    parser = argparse.ArgumentParser(description="Analyze Bulk Extractor EXIF output for location indicators.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug printing (writes to stderr).")
    parser.add_argument("-r", "--regress", action="store_true", help="Run regression tests and exit.")
    args_regress = parser.parse_known_args()[0]

##  Set up regular expressions for extracting desired EXIF tags
    relatref = re.compile(br"<Exif.GPSInfo.GPSLatitudeRef>(?P<GPSLatitudeRef>[NS])\</Exif.GPSInfo.GPSLatitudeRef>")
    relongref = re.compile(br"<Exif.GPSInfo.GPSLongitudeRef>(?P<GPSLongitudeRef>[EW])</Exif.GPSInfo.GPSLongitudeRef>")
    relat = re.compile(br"<Exif.GPSInfo.GPSLatitude>(?P<GPSLatitude>[0-9\-/ ]{1,40})</Exif.GPSInfo.GPSLatitude>")
    relong = re.compile(br"<Exif.GPSInfo.GPSLongitude>(?P<GPSLongitude>[0-9\-/ ]{1,40})</Exif.GPSInfo.GPSLongitude>")
    retimestamp = re.compile(br"<Exif.GPSInfo.GPSTimeStamp>(?P<GPSTimeStamp>[0-9/ ]{1,40})</Exif.GPSInfo.GPSTimeStamp>")
    redatestamp = re.compile(br"<Exif.GPSInfo.GPSDateStamp>(?P<GPSDateStamp>[0-9: .]{1,40})</Exif.GPSInfo.GPSDateStamp>")
    redatetime  = re.compile(br"<Exif.Image.DateTime>(?P<DateTime>[0-9: .]{1,40})</Exif.Image.DateTime>")
    
    if args_regress.regress:
        assert round(dms_to_decimal(b"33/1 49/1 42/1"), 4) == 33.8283
        assert round(dms_to_decimal(b"33/1 49/1 0/1"), 4) == round(dms_to_decimal(b"33/1 49/1"), 4)
        assert dms_to_decimal(b"0/0 0/0 0/0") is None #This value was observed in the Real Data Corpus.
        #TODO assert hms_fraction_to_decimal(b"8/1 49/1 18/1") == "8:49:18"
        #Sample EXIF data supplied by m57-redacted-terry-2009-12-07.aff, image offset 2116743168, pretty-printed with xmllint
        test_exif = b"""<?xml version="1.0"?>
<exif>
  <width>48</width>
  <height>48</height>
  <Exif.Image.Make>Apple</Exif.Image.Make>
  <Exif.Image.Model>iPhone</Exif.Image.Model>
  <Exif.Image.XResolution>72/1</Exif.Image.XResolution>
  <Exif.Image.YResolution>72/1</Exif.Image.YResolution>
  <Exif.Image.ResolutionUnit>2</Exif.Image.ResolutionUnit>
  <Exif.Image.DateTime>2008:11:26 11:46:56</Exif.Image.DateTime>
  <Exif.Image.ExifTag>180</Exif.Image.ExifTag>
  <Exif.Photo.FNumber>14/5</Exif.Photo.FNumber>
  <Exif.Photo.DateTimeOriginal>2008:11:26 11:46:56</Exif.Photo.DateTimeOriginal>
  <Exif.Photo.DateTimeDigitized>2008:11:26 11:46:56</Exif.Photo.DateTimeDigitized>
  <Exif.Photo.ColorSpace>1</Exif.Photo.ColorSpace>
  <Exif.Photo.PixelXDimension>1200</Exif.Photo.PixelXDimension>
  <Exif.Photo.PixelYDimension>1600</Exif.Photo.PixelYDimension>
  <Exif.Image.GPSTag>306</Exif.Image.GPSTag>
  <Exif.GPSInfo.GPSLatitudeRef>N</Exif.GPSInfo.GPSLatitudeRef>
  <Exif.GPSInfo.GPSLatitude>38/1 5354/100 0/1</Exif.GPSInfo.GPSLatitude>
  <Exif.GPSInfo.GPSLongitudeRef>W</Exif.GPSInfo.GPSLongitudeRef>
  <Exif.GPSInfo.GPSLongitude>92/1 2343/100 0/1</Exif.GPSInfo.GPSLongitude>
  <Exif.GPSInfo.GPSTimeStamp>11/1 46/1 788/100</Exif.GPSInfo.GPSTimeStamp>
  <Exif.Image.0xa500>11/5</Exif.Image.0xa500>
  <Exif.Thumbnail.Compression>6</Exif.Thumbnail.Compression>
  <Exif.Thumbnail.Orientation>6</Exif.Thumbnail.Orientation>
  <Exif.Thumbnail.XResolution>72/1</Exif.Thumbnail.XResolution>
  <Exif.Thumbnail.YResolution>72/1</Exif.Thumbnail.YResolution>
  <Exif.Thumbnail.ResolutionUnit>2</Exif.Thumbnail.ResolutionUnit>
  <Exif.Thumbnail.JPEGInterchangeFormat>550</Exif.Thumbnail.JPEGInterchangeFormat>
  <Exif.Thumbnail.JPEGInterchangeFormatLength>11682</Exif.Thumbnail.JPEGInterchangeFormatLength>
</exif>"""
        assert not relat.search(test_exif) is None
        assert not relong.search(test_exif) is None
        assert relatref.search(test_exif).group("GPSLatitudeRef") == b"N"
        assert relongref.search(test_exif).group("GPSLongitudeRef") == b"W"
        exit(0)

    parser.add_argument("-a", "--anno", help="Annotation database of Fiwalk and TSK-db")
    parser.add_argument("exif_file", type=argparse.FileType('rb'), help="Bulk Extractor exif.txt")
    args = parser.parse_args()

    dprint("Debug: args.anno = %r.\n" % args.anno)

##  Connect to db
    cfg = geoproc_cfg.config
    refconn = mysql.connector.Connect(
      host=cfg.get("mysql", "maxmind_server"),
      user=cfg.get("mysql", "maxmind_read_username"),
      password=geoproc_cfg.db_password("maxmind_read_password_file"),
      db=cfg.get("mysql", "maxmind_schema"),
      use_unicode=True
    )
    if refconn is None:
      raise Exception("Error: Could not define lookup cursor.")
    refcur = refconn.cursor(cursor_class=geoproc_cfg.MySQLCursorDict)

##  Connect to output db
    outconn = sqlite3.connect("exif_headers_votes.db")
    outconn.isolation_level = "EXCLUSIVE"
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()
    outcur.execute(SQL_CREATE_EXIF_HEADERS_VOTES)

##  Connect to anno db if available
    annoconn, annocur = geoproc_library.connect_to_fs_anno_db(args.anno)

    for binary_line in args.exif_file:
        binary_line_parts = binary_line.split(b"\t")
        if len(binary_line_parts) < 3:
            #We don't even have exif data. Skip.
            continue
        recdict = dict()
        recdict["forensic_path"] = str(binary_line_parts[0], "ascii")
        exif_data = binary_line_parts[2]
        match_exif_gps_lat = relat.search(exif_data)
        match_exif_gps_lon = relong.search(exif_data)
        #The above matches are essential
        if None in [match_exif_gps_lat, match_exif_gps_lon]:
            continue

        exif_gps_lat_decimal = dms_to_decimal(match_exif_gps_lat.group("GPSLatitude"))
        exif_gps_lon_decimal = dms_to_decimal(match_exif_gps_lon.group("GPSLongitude"))
        try:
            if not None in [exif_gps_lat_decimal, exif_gps_lon_decimal]:
                recdict["exif_gps_lat"] = round(exif_gps_lat_decimal, 4)
                recdict["exif_gps_lon"] = round(exif_gps_lon_decimal, 4)
        except IndexError:
            #Didn't find lat or long content. Warn and continue.
            sys.stderr.write("Warning: Couldn't find a lat (maybe long) from these matches:\n\t%r\n\t%r\n" % (match_exif_gps_lat.group(0), match_exif_gps_lon.group(0)))

        #This script's only purpose is finding lat/longs
        if None in [recdict.get("exif_gps_lat"), recdict.get("exif_gps_lon")]:
            continue

        #Lat/long references, we can guess: Default to N,E.
        match_exif_gps_latref = relatref.search(exif_data)
        match_exif_gps_longref = relongref.search(exif_data)
        exif_gps_latref = b"N"
        if match_exif_gps_latref:
            exif_gps_latref = match_exif_gps_latref.group("GPSLatitudeRef")
        exif_gps_longref = b"E"
        if match_exif_gps_longref:
            exif_gps_longref = match_exif_gps_longref.group("GPSLongitudeRef")

        if exif_gps_latref == b"S":
            recdict["exif_gps_lat"] *= -1
        if exif_gps_longref == b"W":
            recdict["exif_gps_lon"] *= -1

        #Times, we can guess from the file if we really need to.
        match_exif_timestamp = retimestamp.search(exif_data)
        if match_exif_timestamp:
            recdict["exif_gps_timestamp"] = hms_fraction_to_decimal(match_exif_timestamp.group("GPSTimeStamp"))
        match_exif_datestamp = redatestamp.search(exif_data)
        if match_exif_datestamp:
            recdict["exif_gps_datestamp"] = match_exif_datestamp.group("GPSDateStamp")
        match_exif_datetime = redatetime.search(exif_data)
        if match_exif_datetime:
            recdict["exif_datetime"] = match_exif_datetime.group("DateTime")
        #TODO integrate times into output

        refrecs = geoproc_library.latlongs_to_networked_locations(refcur, recdict["exif_gps_lat"], recdict["exif_gps_lon"], 30)
        if refrecs is None:
            recdict["database_queried"] = False
        else:
            recdict["database_queried"] = True
            #Get the nearest city within 30 miles
            if len(refrecs) > 0 and refrecs[0]["distance_miles"] < 30:
                refrec = refrecs[0]
                recdict["country"] = refrec["country"]
                recdict["region"] = refrec["region"]
                recdict["city"] = refrec["city"]
                recdict["postalCode"] = refrec["postalCode"]
                recdict["distance_miles"] = refrec["distance_miles"]

        #Note the name of the file containing this EXIF data, if available
        annorecs = geoproc_library.forensic_path_to_anno_recs(annocur, recdict["forensic_path"])

        if annorecs and len(annorecs) > 0:
            for annorec in annorecs:
                outdict = copy.deepcopy(recdict)
                outdict["fs_obj_id"] = annorec.get("fs_obj_id")
                outdict["obj_id"] = annorec.get("obj_id")
                outdict["fiwalk_id"] = annorec.get("fiwalk_id")

                #Look at file system path and say if we think it's in a cache
                if outdict.get("obj_id"):
                    annocur.execute("""
                      SELECT
                        full_path
                      FROM
                        tsk_file_full_paths
                      WHERE
                        obj_id = ?;
                    """, (outdict["obj_id"],))
                    pathrows = [row for row in annocur]
                    if len(pathrows) == 1:
                        outdict["file_in_web_cache"] = geoproc_library.path_in_web_cache(pathrows[0]["full_path"])

                #Output
                geoproc_library.insert_db(outcur, "exif_headers_votes", outdict)
        else:
            #Output to database without owning-file annotations
            geoproc_library.insert_db(outcur, "exif_headers_votes", recdict)
    outconn.commit()

if __name__ == "__main__":
    main()
