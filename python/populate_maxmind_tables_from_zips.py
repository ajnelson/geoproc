#!/usr/bin/env python3
"""
To see usage information, run without arguments, or see 'parser =' variable definition line.
"""

__version__ = "0.3.0"

import mysql.connector as mdb
import sys,os
import csv
import argparse
import datetime
import zipfile

#Python3 CSV 'bytes' error resolved with a TextIOWrapper. C/o: <http://stackoverflow.com/a/5639960/1207160>
import io

import geoproc_cfg

def datetime_from_ziptime(t):
    """
    Returns a datetime.datetime() object initiated from a sextuple of year, month, day, hour, minute, second.
    """
    if len(t) != 6:
        raise ValueError("Expected a sextuple for datetime conversion.  Got: %r." % t)
    return datetime.datetime(t[0], t[1], t[2], t[3], t[4], t[5])

SQL_CREATE_ingest_audit_zips = """
CREATE TABLE IF NOT EXISTS ingest_audit_zips(
  zip_basename TEXT,
  zip_full_path TEXT,
  datetime_start DATETIME,
  datetime_end DATETIME
);
"""

SQL_CREATE_ingest_audit_locations = """
CREATE TABLE IF NOT EXISTS ingest_audit_locations(
  zip_basename TEXT,
    mtime DATETIME,
    datetime_start DATETIME,
    datetime_end DATETIME
);
"""

SQL_CREATE_ingest_audit_blocks = """
CREATE TABLE IF NOT EXISTS ingest_audit_blocks(
  zip_basename TEXT,
  mtime DATETIME,
  datetime_start DATETIME,
  datetime_end DATETIME
);
"""

SQL_CREATE_LocationTable = """
CREATE TABLE IF NOT EXISTS LocationTable(
  locId BIGINT,
  lastModifiedTime datetime,
  country VARCHAR(255) CHARACTER SET utf8,
  region VARCHAR(255) CHARACTER SET utf8,
  city VARCHAR(255) CHARACTER SET utf8,
  postalCode TEXT,
  latitude FLOAT,
  longitude FLOAT,
  metroCode TEXT,
  areaCode TEXT,
  CONSTRAINT loc_pk PRIMARY KEY USING BTREE (lastModifiedTime, locId)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
"""

SQL_CREATE_BlockTable = """
CREATE TABLE IF NOT EXISTS BlockTable(
  startIpNum BIGINT,
  endIpNum BIGINT,
  locId BIGINT,
  lastModifiedTime datetime,
  CONSTRAINT time_startip_pk PRIMARY KEY USING BTREE (lastModifiedTime, startIpNum)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
"""

#Note that these column types must match the corresponding entries in LocationTable
SQL_CREATE_LocationLatLongs = """
CREATE TABLE IF NOT EXISTS LocationLatLongs (
  latlong POINT NOT NULL,
  locId BIGINT,
  lastModifiedTime datetime,
  SPATIAL INDEX latlong_index (latlong)
) ENGINE=MyISAM;
"""

SQL_DROP_DistinctLocations = """
DROP TABLE IF EXISTS DistinctLocations;
"""

SQL_CREATE_DistinctLocations = """
CREATE TABLE DistinctLocations AS
  SELECT DISTINCT
    country,
    region,
    city
  FROM
    LocationTable
  ORDER BY
    country, city, region
;
"""

def main():
##  The program outline is embedded inline with double-hash comments (fit for grepping).

##  Parse parameters
    parser = argparse.ArgumentParser(description="Create and populate MySQL database with MaxMind data.")
    parser.add_argument("-r", "--regress", action="store_true", dest="regress", help="Run unit tests and exit.  Requires database connection.")
    parser.add_argument("-d", "--debug", action="store_true", dest="debug", help="Print debug information to stderr.")
    parser.add_argument("zips", help="Text file of MaxMind zips to ingest, one absolute path per line; or a directory containing the zips; or just one zip.")
    args = parser.parse_args()
    
    input_file_list = []
    if args.zips.endswith(".zip"):
        input_file_list.append(os.path.abspath(os.path.expanduser(args.zips)))
    elif os.path.isdir(args.zips):
        for zipdirentry in os.listdir(args.zips):
            if zipdirentry.endswith(".zip"):
                input_file_list.append(os.path.abspath(os.path.join(args.zips, zipdirentry)))
    else:
        with open(args.zips, "r") as inputFile:
            for line in inputFile:
                maxmind_zip_path = line.strip()
                if not os.path.isabs(maxmind_zip_path):
                    raise ValueError("Paths in ziplist file must be absolute.")
                input_file_list.append(maxmind_zip_path)
            
##  Connect to db
    #Not using a try block - the whole point of this script is filling the database
    config = geoproc_cfg.config
    con = mdb.Connect(
      host=config.get("mysql", "maxmind_server"),
      user=config.get("mysql", "maxmind_write_username"),
      password=geoproc_cfg.db_password("maxmind_write_password_file"),
      db=config.get("mysql", "maxmind_schema"),
      use_unicode=True
    )
    cur = con.cursor(cursor_class=geoproc_cfg.MySQLCursorDict)
    cur.execute("SET NAMES 'utf8';")

##  Run regress tests?
        #TODO
        
##  Create tables if non-existent
    if args.debug:
        sys.stderr.write("Creating tables...\n")
    #Datetime vs timestamp: <http://stackoverflow.com/a/409305/1207160>
    cur.execute(SQL_CREATE_ingest_audit_zips)
    cur.execute(SQL_CREATE_ingest_audit_locations)
    cur.execute(SQL_CREATE_ingest_audit_blocks)
    cur.execute(SQL_CREATE_LocationTable)
    cur.execute(SQL_CREATE_BlockTable)
    cur.execute(SQL_CREATE_LocationLatLongs)
            
##  Record the number of location tables processed - non-zero triggers a table refresh later
    tally_location_updates = 0
    

##  Read table of processed zip files
##      # Should contain: Zip file base name, full path to zip file, datetime started, datetime ended
##  Read table of processed block files
##      # Should contain: Zip file base name (foreign key), mtime, datetime started, datetime ended
##  Read table of processed location files
##      # Should contain: Zip file base name (foreign key), mtime, datetime started, datetime ended
##  Read input list of zip files to ingest
    for maxmind_zip_path in input_file_list:
        maxmind_zip_basename = os.path.basename(maxmind_zip_path)
##  For each zip in the list:
##      If the zip had not finished processing previously:
        previously_finished_zip = False
        reset_this_zip = False
        cur.execute("SELECT * FROM ingest_audit_zips WHERE zip_basename = %s;", (maxmind_zip_basename,))
        for row in cur.fetchall():
            if row["datetime_end"] is None:
                #This row shouldn't be here at all.
                reset_this_zip = True
            else:
                previously_finished_zip = True
        if previously_finished_zip:
            sys.stderr.write("Warning: Zip file already read into database... Skipping zip file:" + maxmind_zip_path + "\n")
            continue

##          If the block file had started and not finished previously:
        cur.execute("SELECT * FROM ingest_audit_blocks WHERE zip_basename = %s AND datetime_start IS NOT NULL AND datetime_end IS NULL;", (maxmind_zip_basename,))
        rows = [row for row in cur.fetchall()]
        for row in rows:
            sys.stderr.write("Note: Found incomplete Block ingest for zip %r, started %r. Deleting records.\n" % (row["zip_basename"], row["datetime_start"]))
##              Delete block records with matching mtime
            cur.execute("DELETE FROM BlockTable WHERE lastModifiedTime = %s;", (row["mtime"],))
        if len(rows) > 0:
            cur.execute("DELETE FROM ingest_audit_blocks WHERE zip_basename = %s AND datetime_end IS NULL;", (maxmind_zip_basename,))

##          If the location file had started and not finished previously:
        cur.execute("SELECT * FROM ingest_audit_locations WHERE zip_basename = %s AND datetime_start IS NOT NULL AND datetime_end IS NULL;", (maxmind_zip_basename,))
##              Delete block records with matching mtime
        rows = [row for row in cur.fetchall()]
        for row in rows:
            sys.stderr.write("Note: Found incomplete Location ingest for zip %r, started %r. Deleting records.\n" % (row["zip_basename"], row["datetime_start"]))
            cur.execute("DELETE FROM LocationLatLongs WHERE lastModifiedTime = %s;", (row["mtime"],))
            cur.execute("DELETE FROM LocationTable WHERE lastModifiedTime = %s;", (row["mtime"],))
        if len(rows) > 0:
            cur.execute("DELETE FROM ingest_audit_locations WHERE zip_basename = %s AND datetime_end IS NULL;", (maxmind_zip_basename,))

##          Mark start time for processing zip
        starttime_zip = datetime.datetime.now()
        if reset_this_zip:
            cur.execute("DELETE FROM ingest_audit_zips WHERE zip_basename = %s;", (maxmind_zip_basename,))
        #strftime appears to be the way to insert datetimes from Python to MySQL <http://stackoverflow.com/a/4508923/1207160>
        cur.execute("INSERT INTO ingest_audit_zips(zip_basename, zip_full_path, datetime_start) VALUES (%s,%s,%s);", (maxmind_zip_basename, maxmind_zip_path, datetime.datetime.strftime(starttime_zip, "%Y-%m-%d %H:%M:%S")))
        con.commit()

##          Get zip internal listing
        with zipfile.ZipFile(maxmind_zip_path, "r") as this_zip:
            zipped_blocks_name = None
            zipped_locations_name = None
            for zi in this_zip.infolist():
                if zi.filename.endswith("Location.csv"):
                    zipped_locations_name = zi.filename
                    zipped_locations_time = datetime_from_ziptime(zi.date_time)
                elif zi.filename.endswith("Blocks.csv"):
                    zipped_blocks_name = zi.filename
                    zipped_blocks_time = datetime_from_ziptime(zi.date_time)

##          If the location file had not finished processing previously:
            should_process_locations = False
            if zipped_locations_name is not None:
                zipped_locations_time_str = datetime.datetime.strftime(zipped_locations_time, "%Y-%m-%d %H:%M:%S")
                cur.execute("SELECT COUNT(*) AS tally FROM ingest_audit_locations WHERE zip_basename = %s AND datetime_end IS NOT NULL;", (maxmind_zip_basename,))
                for rec in cur.fetchall():
                    should_process_locations = (rec["tally"] == 0)
            if should_process_locations:        
##              Mark start time
                starttime_locations = datetime.datetime.now()
                cur.execute("INSERT INTO ingest_audit_locations(zip_basename, mtime, datetime_start) VALUES (%s,%s,%s);", (maxmind_zip_basename, zipped_locations_time_str, datetime.datetime.strftime(starttime_locations, "%Y-%m-%d %H:%M:%S")))
                con.commit()
##              Ingest
                with this_zip.open(zipped_locations_name, "r") as locations_file:
                    if args.debug:
                        sys.stderr.write("Note: Ingesting %s / %s...\n" % (maxmind_zip_path, zipped_locations_name))
                    lineCount = 0
                    locations_file_wrapped = io.TextIOWrapper(locations_file, encoding="iso-8859-1") #MaxMind content encoding: http://dev.maxmind.com/geoip/csv
                    locations_reader = csv.reader(locations_file_wrapped, delimiter=',', quoting=csv.QUOTE_ALL)
                    for row in locations_reader:
                        if len(row) == 9  and row[0].isdigit():
                            cur.execute("INSERT INTO LocationTable VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (int(row[0]),zipped_locations_time_str,row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8] ))
                        lineCount = lineCount + 1
                        if lineCount % 10000 == 0 :
                            if args.debug:
                                sys.stderr.write("\tOn locations CSV record %d...\n" % lineCount)
                            con.commit()
                    con.commit()
##              Update lat/long index
                if args.debug:
                    sys.stderr.write("Note: Updating lat/long index.\n")
                cur.execute("""
                  INSERT INTO LocationLatLongs (latlong, locId, lastModifiedTime)
                    SELECT
                      POINT(latitude, longitude),
                      locId,
                      lastModifiedTime
                    FROM
                      LocationTable
                    WHERE
                      lastModifiedTime = %s
                    ;
                """, (zipped_locations_time_str,))
                con.commit()
##              Mark end time
                endtime_locations = datetime.datetime.now()
                cur.execute("UPDATE ingest_audit_locations SET datetime_end = %s WHERE zip_basename = %s;", (datetime.datetime.strftime(endtime_locations, "%Y-%m-%d %H:%M:%S"), maxmind_zip_basename))
                con.commit()
                tally_location_updates += 1

##          If the block file had not finished processing previously:
            should_process_blocks = False
            if zipped_blocks_name is not None:
                zipped_blocks_time_str = datetime.datetime.strftime(zipped_blocks_time, "%Y-%m-%d %H:%M:%S")
                cur.execute("SELECT COUNT(*) AS tally FROM ingest_audit_blocks WHERE zip_basename = %s AND datetime_end IS NOT NULL;", (maxmind_zip_basename,))
                for rec in cur.fetchall():
                    should_process_blocks = (rec["tally"] == 0)
            if should_process_blocks:        
##              Mark start time
                starttime_blocks = datetime.datetime.now()
                cur.execute("INSERT INTO ingest_audit_blocks(zip_basename, mtime, datetime_start) VALUES (%s,%s,%s);", (maxmind_zip_basename, zipped_blocks_time_str, datetime.datetime.strftime(starttime_blocks, "%Y-%m-%d %H:%M:%S")))
                con.commit()
##              Ingest
                with this_zip.open(zipped_blocks_name, "r") as blocks_file:
                    if args.debug:
                        sys.stderr.write("Note: Ingesting %s / %s...\n" % (maxmind_zip_path, zipped_blocks_name))
                    lineCount = 0
                    blocks_file_wrapped = io.TextIOWrapper(blocks_file, encoding="iso-8859-1") #MaxMind content encoding: http://dev.maxmind.com/geoip/csv
                    blocks_reader = csv.reader(blocks_file_wrapped, delimiter=',', quoting=csv.QUOTE_ALL)
                    for row in blocks_reader:
                        if len(row) == 3  and row[0].isdigit():
                            cur.execute("INSERT INTO BlockTable VALUES(%s,%s,%s,%s)", (row[0],row[1],row[2],zipped_blocks_time_str))
                        lineCount = lineCount + 1
                        if lineCount % 10000 == 0 :
                            if args.debug:
                                sys.stderr.write("\tOn blocks CSV record %d...\n" % lineCount)
                            con.commit()
                    con.commit()
##              Mark end time
                endtime_blocks = datetime.datetime.now()
                cur.execute("UPDATE ingest_audit_blocks SET datetime_end = %s WHERE zip_basename = %s;", (datetime.datetime.strftime(endtime_blocks, "%Y-%m-%d %H:%M:%S"), maxmind_zip_basename))
                con.commit()
##          Mark end time
        endtime_blocks = datetime.datetime.now()
        cur.execute("UPDATE ingest_audit_zips SET datetime_end = %s WHERE zip_basename = %s;", (datetime.datetime.strftime(endtime_blocks, "%Y-%m-%d %H:%M:%S"), maxmind_zip_basename))
        con.commit()
    #If we updated the LocationTable, refresh the list of all distinct location triples
    if tally_location_updates > 0:
        if args.debug:
            sys.stderr.write("Note: Refreshing DistinctLocations table.\n")
        cur.execute(SQL_DROP_DistinctLocations)
        cur.execute(SQL_CREATE_DistinctLocations)
        for locfield in ["country", "region", "city"]:
            formatdict = {"locfield":locfield}
            cur.execute("DROP TABLE IF EXISTS Distinct_%(locfield)s;" % formatdict)
            con.commit()
            cur.execute("""
              CREATE TABLE Distinct_%(locfield)s AS
              SELECT DISTINCT
                %(locfield)s
              FROM
                DistinctLocations
              WHERE
                %(locfield)s IS NOT NULL AND
                %(locfield)s <> ""
              ORDER BY
                %(locfield)s
              ;
            """ % formatdict)
        con.commit()
##  Done.

    if con:
        con.close()

if __name__ == "__main__":
   main()
