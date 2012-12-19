#!/usr/bin/env python3

__version__ = "0.4.6"

import argparse
import sys
import os
import sqlite3

import mysql.connector as mdb

import geoproc_cfg
import geoproc_library
import success

import analyze_cookie_files
import analyze_email_files
import analyze_exif_headers
import analyze_ipv4s

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

LOCATION_COLUMNS = ["country", "region", "city"]

lookup_memoizer = dict()
gt_memoizer = dict()

def ingest_table(outcur, lookupcur, gtcur, results_dir, scriptname, dbname, tablename):
    global args
    global lookup_memoizer
    if success.success(os.path.join(results_dir, scriptname + ".status.log")):
        image_id = os.path.basename(results_dir)
        dprint("Debug: image_id: %r" % image_id)
        dprint("Debug: results_dir: %r" % results_dir)
        dprint("Debug: scriptname: %r" % scriptname)
        dprint("Debug: dbname: %r" % dbname)
        try:
            results_conn = sqlite3.connect(os.path.join(results_dir, scriptname, dbname))
        except:
            raise
        results_conn.row_factory = sqlite3.Row
        results_conn.isolation_level = "EXCLUSIVE" #lock database
        results_cur = results_conn.cursor()
        results_cur.execute("SELECT * FROM %s;" % tablename)
        #Check if we're counting ground truth for this image
        image_ground_truth_available = False
        if gtcur is not None:
            gtcur.execute("SELECT COUNT(*) AS tally FROM location_ground_truth WHERE image_id = ?;", (image_id,))
            gtrows = [row for row in gtcur]
            image_ground_truth_available = gtrows[0]["tally"] > 0
        for row in results_cur:
            outdict = {k:row[k] for k in row.keys()}
            outdict["image_id"] = image_id
            geoproc_library.insert_db(outcur, tablename, outdict)
            if gtcur is not None and image_ground_truth_available:
                list_vals = []
                non_null_results_cols = [bcol for bcol in LOCATION_COLUMNS if outdict.get(bcol)]
                sqlite3_extra_where = ""
                mysql_extra_where = ""
                for bcol in non_null_results_cols: 
                    #This sqlite query matches in the case where ground truth is not city-granularity
                    sqlite3_extra_where += " AND (" + bcol + " = ? OR " + bcol + " IS NULL)"
                    mysql_extra_where +=   " AND " + bcol + " = %s"
                    list_vals.append(outdict[bcol])
                #Make sure the search has at least one narrowing component
                if len(list_vals) == 0:
                    continue
                if not (sqlite3_extra_where, tuple([image_id] + list_vals)) in gt_memoizer:
                    gtquery = "SELECT country,region,city FROM location_ground_truth WHERE image_id = ?"
                    gtquery += sqlite3_extra_where + ";"
                    gtcur.execute(gtquery, tuple([image_id] + list_vals))
                    gt_memoizer[(sqlite3_extra_where, tuple([image_id] + list_vals))] = [(row["country"], row["region"], row["city"]) for row in gtcur]
                if not (mysql_extra_where, tuple(list_vals)) in lookup_memoizer:
                    lookupquery = "SELECT country,region,city FROM DistinctLocations WHERE 1=1"
                    lookupquery += mysql_extra_where + ";"
                    lookupcur.execute(lookupquery, tuple(list_vals))
                    lookup_memoizer[(mysql_extra_where, tuple(list_vals))] = [(row["country"], row["region"], row["city"]) for row in lookupcur]
                gtrecs = gt_memoizer[(sqlite3_extra_where, tuple([image_id] + list_vals))]
                lookuprecs = lookup_memoizer[(mysql_extra_where, tuple(list_vals))]
                #dprint("Debug: lookupquery = %r." % lookupquery)
                #dprint("Debug: list_vals = %r." % list_vals)
                #Get worldwide number of matching locations if one of the fields is missing
                dprint("Debug: len(lookuprecs) = %d." % len(lookuprecs))
                #Mark current vote correct by counting the number of matches in the ground truth query
                outdict["correct_location"] = len([rec for rec in gtrecs if (outdict["country"], outdict["region"], outdict["city"]) == rec])
                for (colno, col) in enumerate(LOCATION_COLUMNS):
                    outdict["correct_" + col] = len([rec for rec in gtrecs if rec[colno] == outdict[col]])
                outdict["number_possible_locations"] = len(lookuprecs)
                geoproc_library.insert_db(outcur, tablename + "_weighted", outdict)
        results_conn.close()

def main():
    global args

    if os.path.isfile(args.output_db):
        if args.zap:
            os.remove(args.output_db)
        else:
            raise Exception("Output database already exists; aborting.")

    #Connect to location database to get names (necessary for wildcard matching, like if we just found a city)
    config = geoproc_cfg.config
    lookupconn = mdb.Connect(
      host=config.get("mysql", "maxmind_server"),
      user=config.get("mysql", "maxmind_read_username"),
      password=geoproc_cfg.db_password("maxmind_read_password_file"),
      db=config.get("mysql", "maxmind_schema"),
      use_unicode=True
    )
    lookupcur = lookupconn.cursor(cursor_class=geoproc_cfg.MySQLCursorDict)

    #Maybe connect to ground truth
    gtconn = None
    gtcur = None
    if args.ground_truth:
        gtconn = sqlite3.connect(args.ground_truth)
        gtconn.row_factory = sqlite3.Row
        #Don't lock database
        gtcur = gtconn.cursor()

    results_dir_list = geoproc_library.get_results_dirs(args.input_root)
    dprint("Aggregating %d directories." % len(results_dir_list))

    #Connect to output database
    outconn = sqlite3.connect(args.output_db)
    outconn.isolation_level = "EXCLUSIVE"
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()

    def add_columns(outcur, table_name):
        #Simple aggregate table: Just gets column for image_id
        outcur.execute("ALTER TABLE %s ADD COLUMN image_id TEXT;" % table_name)

        #Weighted aggregate table: Gets other columns to determine vote accuracy
        outcur.execute("CREATE TABLE %s_weighted AS SELECT * FROM %s;" % (table_name, table_name))
        outcur.execute("ALTER TABLE %s_weighted ADD COLUMN number_possible_locations NUMBER" % table_name)
        for bcol in ["country", "region", "city", "location"]:
            outcur.execute("ALTER TABLE %s_weighted ADD COLUMN correct_%s NUMBER;" % (table_name, bcol))

    outcur.execute(analyze_cookie_files.SQL_CREATE_COOKIE_FILES_VOTES)
    add_columns(outcur, "cookie_files_votes")
    outcur.execute(analyze_email_files.SQL_CREATE_EMAIL_FILES_VOTES)
    add_columns(outcur, "email_files_votes")
    outcur.execute(analyze_exif_headers.SQL_CREATE_EXIF_HEADERS_VOTES)
    add_columns(outcur, "exif_headers_votes")
    outcur.execute(analyze_ipv4s.SQL_CREATE_IPV4S_VOTES)
    add_columns(outcur, "ipv4s_votes")

    for results_dir in results_dir_list:
        try:
            ingest_table(outcur, lookupcur, gtcur, results_dir, "analyze_cookie_files.sh", "cookie_files_votes.db", "cookie_files_votes")
            ingest_table(outcur, lookupcur, gtcur, results_dir, "analyze_email_files.sh", "email_files_votes.db", "email_files_votes")
            ingest_table(outcur, lookupcur, gtcur, results_dir, "analyze_exif_headers.sh", "exif_headers_votes.db", "exif_headers_votes")
            ingest_table(outcur, lookupcur, gtcur, results_dir, "analyze_ipv4s.sh", "ipv4s_votes.db", "ipv4s_votes")
        except:
            dprint("Debug: Error occurred on results_dir %r." % results_dir)
            raise
    outconn.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate output from a list of geoproc 'process' output directories.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug printing (writes to stderr).")
    parser.add_argument("-r", "--regress", action="store_true", help="Run regression tests and exit.")

    args_regress = parser.parse_known_args()[0]
    if args_regress.regress:
        #Test the existence of the SQL statements we're importing
        assert analyze_cookie_files.SQL_CREATE_COOKIE_FILES_VOTES
        assert analyze_email_files.SQL_CREATE_EMAIL_FILES_VOTES
        assert analyze_exif_headers.SQL_CREATE_EXIF_HEADERS_VOTES
        assert analyze_ipv4s.SQL_CREATE_IPV4S_VOTES

        #Test a not-too-obvious behavior of ArgumentParser, that the same option passed multiple times retains only the last value
        test_parser = argparse.ArgumentParser()
        test_parser.add_argument("--foo")
        test_args0 = test_parser.parse_args("--foo bar".split())
        assert test_args0.foo == "bar"
        test_args1 = test_parser.parse_args("--foo bar --foo asdf".split())
        assert test_args1.foo == "asdf"

        sys.exit(0)

    parser.add_argument("-z", "--zap", action="store_true", help="Remove output_db if it already exists.")
    parser.add_argument("--ground_truth", help="SQLite database file housing location ground truth for images.  Note that a default value from installed data is passed via the geoproc.sh interface.")
    parser.add_argument("input_root", help="Directory that houses geoproc 'process' output from one or more images.")
    parser.add_argument("output_db", help="Name of the SQLite database to write.  Must not exist.")
    args = parser.parse_args()
    main()
