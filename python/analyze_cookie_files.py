#!/usr/bin/env python3

"""
Process extracted cookie files for geographic indicators.

Name scheme assumption: The cookie extraction process names its dumped files with the Fiwalk identifier number (as in DFXML).
"""

__version__ = "0.5.0"

import os
import sys
import re
import argparse
import traceback
import sqlite3
import geoproc_cfg
import geoproc_library
import copy
import dfxml


SQL_CREATE_COOKIE_FILES_VOTES = """CREATE TABLE cookie_files_votes (
  record_type TEXT,
  forensic_path TEXT,
  fiwalk_id NUMBER,
  fs_obj_id NUMBER,
  obj_id NUMBER,
  ipv4 TEXT,
  network_proxy_software_detected BOOLEAN,
  believed_timestamp TEXT,
  maxmind_ipv4_time TEXT,
  country TEXT,
  region TEXT,
  city TEXT,
  postalCode TEXT,
  latitude NUMBER,
  longitude NUMBER,
  selected_time_type TEXT,
  country_found_in_text BOOLEAN,
  region_found_in_text BOOLEAN,
  city_found_in_text BOOLEAN,
  cookie_latlong_and_maxmind_agree_on_country BOOLEAN,
  cookie_latlong_and_maxmind_agree_on_postalCode BOOLEAN,
  database_queried BOOLEAN
);"""

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

rx_latlong_msn = re.compile(r"z:(?P<zipcode>[0-9]{5})\|la:(?P<latitude>-?[0-9]{1,3}(\.[0-9]{1,5})?)\|lo:(?P<longitude>-?[0-9]{1,3}(\.[0-9]{1,5})?)(\|c:(?P<countrycode>[A-Z]{2})\|hr:)?")

def all_msn_matches(cookie_contents):
    """
    Returns list of [{zipcode:, latitude:, longitude:, countrycode:}] from a format particular to MSN cookies in at least November-December, 2009.
    If found multiple times, returns all matches.
    If not found, returns empty list.
    """
    global rx_latlong_msn
    return [m.groupdict() for m in rx_latlong_msn.finditer(cookie_contents) if m is not None]

def match_cities(lookupcur, cookie_contents):
    """
    Input: Database connection, entire contents of cookie (this can come from HTTP header or file)
    Output*: All matching location quintuples for cities matching in the contents: City, region(/state) (compressed and not), country (compressed and not)

    *TODO: The unabbreviated names require GeoNames data, so this just returns the regular country, region, dictionary.
    """
    retrecs = []
    if not lookupcur is None:
        for city_pattern in args.distinct_cities:
            partitions = cookie_contents.split(city_pattern)
            if len(partitions) > 1:
                #Query database for all matching cities
                #TODO MaxMind only has the abbreviated region and country names; integrate GeoNames to find better matches.
                lookupcur.execute("""
                    SELECT
                      *
                    FROM
                      DistinctLocations
                    WHERE
                      city = %s
                    ;
                """, (city_pattern,))
                lookuprows = [row for row in lookupcur]
                #Loop over all fenceposts to find near matches
                for i in range(1, len(partitions)):
                    left = city_pattern.join(partitions[:i])
                    right = city_pattern.join(partitions[i:])
                    for lookuprow in lookuprows:
                        region = lookuprow["region"]
                        country = lookuprow["country"]
                        if (region in left or region in right) and \
                          (country in left or country in right):
                            retrecs.append(lookuprow)
    return retrecs


def get_cookie_votes(outconn, lookupcur, annocur, cookie_fiwalk_id, cookie_contents):
    """
    Input: Database connection (if not live, this is nearly a nop), entire contents of cookie (this can come from HTTP header or file)
    Output: All geographic votes from cookie contents
    """
    cookie_contents_lower = cookie_contents.lower()
    retlist = []

    basic_vote = dict()
    basic_vote["fiwalk_id"] = cookie_fiwalk_id

    #Fill in file system info from annodb
    if annocur:
        annocur.execute("""
          SELECT
            tsk_obj_id,
            tf.fs_obj_id,
            tf.mtime,
            tf.atime,
            tf.ctime,
            tf.crtime
          FROM
            fiwalk_id_to_tsk_obj_id,
            tskout.tsk_files AS tf
          WHERE
            fiwalk_id_to_tsk_obj_id.tsk_obj_id = tf.obj_id AND
            fiwalk_id = ?
          ;
        """, (cookie_fiwalk_id,))
        annorows = [row for row in annocur]
        if len(annorows) == 1:
            basic_vote["fs_obj_id"] = annorows[0]["fs_obj_id"]
            basic_vote["obj_id"] = annorows[0]["tsk_obj_id"]
            for timefield in ["mtime", "atime", "ctime", "crtime"]:
                annorow = {key:annorows[0][key] for key in annorows[0].keys()}
                if annorow.get(timefield):
                    basic_vote["selected_time_type"] = timefield
                    basic_vote["believed_timestamp"] = dfxml.dftime(annorow[timefield]).iso8601()
                    break

    #TODO use
    city_matches = match_cities(lookupcur, cookie_contents)

    #Perform MSN matches
    msn_locations = all_msn_matches(cookie_contents)
    for m in msn_locations:
        if not (m.get("longitude") and m.get("latitude")):
            continue
        retdict = copy.deepcopy(basic_vote)
        retdict["record_type"] = "msn"
        retdict["latitude"] = float(m["latitude"])
        retdict["longitude"] = float(m["longitude"])
        if m.get("countrycode"):
            retdict["country"] = m["countrycode"]
            retdict["postalCode"] = m["zipcode"]
        locations_from_latlongs = geoproc_library.latlongs_to_networked_locations(lookupcur, retdict["latitude"], retdict["longitude"], 30)
        if locations_from_latlongs is None:
            sys.stderr.write("Warning: Couldn't look up latitude/longitude.\n")
            retdict["database_queried"] = False
        if locations_from_latlongs is not None and len(locations_from_latlongs) > 0:
            #Use closest location
            locrec = locations_from_latlongs[0]
            for locfield in ["country", "postalCode"]:
                if locrec.get(locfield):
                    if retdict.get(locfield):
                        retdict["cookie_latlong_and_maxmind_agree_on_" + locfield] = locrec[locfield] == retdict[locfield]
                        if not retdict["cookie_latlong_and_maxmind_agree_on_" + locfield]:
                            sys.stderr.write("Warning: Data anomaly: MSN cookie reports %s %r, lat/long seem to be in %r by MaxMind." % (locfield, retdict["country"], locrec["country"]))
                    else:
                        retdict[locfield] = locrec[locfield]
            retdict["region"] = locrec["region"]
            retdict["city"] = locrec["city"]
            retdict["database_queried"] = True
        retlist.append(retdict)

    #Perform IPv4 text matches
    all_ips = geoproc_library.all_ipv4s(cookie_contents)
    for ipv4 in all_ips:
        believed_cookie_time = None #TODO Get actual times from database, loop through them
        all_ip_locations = geoproc_library.ips_to_locations(lookupcur, believed_cookie_time, all_ips)
        retdict = copy.deepcopy(basic_vote)
        retdict["record_type"] = "ipv4"
        retdict["ipv4"] = ipv4
        retdict["database_queried"] = all_ip_locations is not None
        if all_ip_locations is not None and ipv4 in all_ip_locations:
            rec = all_ip_locations[ipv4]
            retdict["latitude"] = rec.get("latitude")
            retdict["longitude"] = rec.get("longitude")
            retdict["postalCode"] = rec.get("postalCode")
            retdict["maxmind_ipv4_time"] = dfxml.dftime(rec.get("maxmind_ipv4_time")).iso8601()
            if rec.get("country"):
                retdict["country"] = rec["country"]
                retdict["country_found_in_text"] = rec["country"].lower() in cookie_contents_lower
            if rec.get("region"):
                retdict["region"] = rec["region"]
                retdict["region_found_in_text"] = rec["region"].lower() in cookie_contents_lower
            if rec.get("city"):
                retdict["city"] = rec["city"]
                retdict["city_found_in_text"] = rec["city"].lower() in cookie_contents_lower
        retlist.append(retdict)
    return retlist

def main():
    cfg = geoproc_cfg.config
    lookupconn = None
    lookupcur = None
    try:
        import mysql.connector as mdb
        lookupconn = mdb.connect(
          host=cfg.get("mysql", "maxmind_server"),
          user=cfg.get("mysql", "maxmind_read_username"),
          password=geoproc_cfg.db_password("maxmind_read_password_file"),
          db=cfg.get("mysql", "maxmind_schema"),
          use_unicode=True
        )
        lookupcur = lookupconn.cursor(cursor_class=geoproc_cfg.MySQLCursorDict)
    except:
        sys.stderr.write("Warning: Could not connect to database. Proceeding without database support.\n")
        pass

    annoconn, annocur = geoproc_library.connect_to_fs_anno_db(args.anno)

    outconn = sqlite3.connect(os.path.join(args.out_dir, "cookie_files_votes.db"))
    outconn.isolation_level = "EXCLUSIVE"
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()
    outcur.execute(SQL_CREATE_COOKIE_FILES_VOTES)
    
    #Walk cookie dump directory
    #TODO? Use a validly-extracted manifest file instead of walking dump directory.
    for (dirpath, dirnames, filenames) in os.walk(args.cookie_dump_dir):
        for cookie_txt_fname in (x for x in filenames if x.endswith("txt")):
            cookie_fiwalk_id = int(os.path.splitext(cookie_txt_fname)[0])
            dprint("Reading cookie_fiwalk_id: %r." % cookie_fiwalk_id)
            with open(os.path.join(dirpath, cookie_txt_fname),"r",encoding="utf-8") as cookie_file:
                try:
                    some_kibs = cookie_file.read(0x8000)
                except:
                    sys.stderr.write("Warning: Reading file %r failed.  Stack trace follows.\n" % cookie_txt_fname)
                    sys.stderr.write(traceback.format_exc())
                    continue
                if len(some_kibs) == 0x8000:
                    sys.stderr.write("Warning: Skipped abnormally large 'cookie' file, >=32KiB: %r.\n" % cookie_txt_fname)
                    continue
                votes = get_cookie_votes(outconn, lookupcur, annocur, cookie_fiwalk_id, some_kibs)
                for vote in votes:
                    geoproc_library.insert_db(outcur, "cookie_files_votes", vote)
    outconn.commit()

##Main program outline
##  For each cookie file:
##      Call processing function that gets all possible votes
##      Upload votes to database

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze cookie files for location information.")
    parser.add_argument("-d","--debug", action="store_true", help="Enable debug messages (writes to stderr).")
    parser.add_argument("-r", "--regress", action="store_true", help="Run regression tests and exit.")
    args_regress = parser.parse_known_args()[0]

    if args_regress.regress:
        #Handy feature of Python: substring search with the "in" operator
        assert "sd" in "asdf"
        
        test_extracted_msn_string = "z:93940|la:36.6|lo:-121.891|c:US|hr:1" #Example source: M57, Charlie, 11-23
        test_extracted_msn = all_msn_matches(test_extracted_msn_string)
        test_extracted_msn_must_match = [{'latitude': '36.6', 'longitude': '-121.891', 'zipcode': '93940', 'countrycode': 'US'}]
        try:
            assert test_extracted_msn == test_extracted_msn_must_match
        except AssertionError as e:
            sys.stderr.write("Error: MSN extraction output differed from expected output.\n")
            sys.stderr.write("\tTest string: %r\n" % test_extracted_msn_string)
            sys.stderr.write("\tExpected output: %r\n" % test_extracted_msn_must_match)
            sys.stderr.write("\tActual output: %r\n" % test_extracted_msn)
            raise e
        testfail_extracted_msn_strings = [
          "z:93940|la:#d.6|lo:-121.891|c:US|hr:1",
          "z:0939|la:36.6|lo:-121.891|c:US|hr:1"
        ]
        for (i, testfail_extracted_msn_string) in enumerate(testfail_extracted_msn_strings):
            testfail_extracted_msn = all_msn_matches(testfail_extracted_msn_string)
            try:
                assert testfail_extracted_msn == []
            except AssertionError as e:
                sys.stderr.write("Error: MSN extraction output differed from expected output.\n")
                sys.stderr.write("\tTest string (index %d in list): %r\n" % (i, testfail_extracted_msn_string))
                sys.stderr.write("\tExpected output: %r\n" % [])
                sys.stderr.write("\tActual output: %r\n" % testfail_extracted_msn)
                raise e
        sys.exit(0)

    parser.add_argument("-a", "--anno", help="TSK+Fiwalk id mapping database")
    parser.add_argument("distinct_cities", type=argparse.FileType('r'), help="File containing city patterns that have matched any of the cookies")
    parser.add_argument("cookie_dump_dir", help="Cookie dump directory")
    parser.add_argument("out_dir", help="Output directory")
    args = parser.parse_args()
    
    main()
