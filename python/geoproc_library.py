
"""
This module defines functions used in multiple places, like IPv4 address identification.
For regression testing, this module can be invoked as a program.
"""

__version__ = "0.9.2"

import re
import sys
import os
import datetime
import math
import traceback
import sqlite3

import bulk_extractor_reader

import geoproc_cfg

#Define regular expression that matches IP addresses
#Excludes strings prefixed with a digit-period, or followed by an optional period and a digit.  This should deal with the granular-version problem.
rx_ipv4_end_ones     = re.compile("(?<![0-9][.])(?P<ip>(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))(?![.]?[0-9])")

#def dprint(s):
#    global args
#    if args.debug:
#        sys.stderr.write(str(s))
#        sys.stderr.write("\n")

def all_ipv4s(intext):
    """
    Returns a set of all IP addresses that match the basic IPv4 quadruplet pattern in the input text.
    """
    #TODO Return instead a dictionary-histogram?
    global rx_ipv4_end_ones
    retset = set([])
    if intext is None:
        return retset
    for match in rx_ipv4_end_ones.finditer(intext):
        if match is None:
            continue
        retset.add(match.groupdict()["ip"])
    return retset

def ip_to_int(ip):
    components = ip.split(".")
    if len(components) != 4:
        return None
    return sum(map(lambda x,y:x*y, [2**24,2**16,2**8,2**0], map(int, components)))

def int_to_ip(ipnum):
    return ".".join(map(str, [
      (ipnum >> 24) % 256,
      (ipnum >> 16) % 256,
      (ipnum >> 8)  % 256,
      (ipnum >> 0)  % 256
    ]))

def ips_to_locations(cur, in_time, ip_list):
    """
    Returns dictionary of IP addresses to location dictionaries (key: ipv4 string, value: dictionary), or None if connection is not live.
    """
    ip_mappings = dict()
    if cur is None:
        return None
    if ip_list is None or len(ip_list) == 0:
        return None
    ips_date_time = in_time
    if ips_date_time is None:
        #TODO Declare a more sensible datetime than this default
        ips_date_time = datetime.datetime(2009, 1, 1, 0, 0, 0)
    ips_to_map = set(ip_list)
    for ip in ips_to_map:
        ip_as_int = ip_to_int(ip)
        if ip_as_int is None:
            continue
        cur.execute("""
          SELECT
            lt.*,
            bt.startIpNum,
            bt.endIpNum,
            bt.endIpNum - bt.startIpNum AS blockSpan
          FROM
            maxmind.BlockTable AS bt,
            maxmind.LocationTable AS lt,
            (
              SELECT
                lastModifiedTime
              FROM
                maxmind.LocationTable
              WHERE
                lastModifiedTime >= %s
              ORDER BY
                lastModifiedTime ASC
              LIMIT 1
            ) AS NextTime
          WHERE
            lt.lastModifiedTime = NextTime.lastModifiedTime AND
            lt.locId = bt.locId AND
            %s BETWEEN bt.startIpNum AND bt.endIpNum
          ORDER BY
            blockSpan;
        """, (ips_date_time, ip_as_int))
        returned_records = [row for row in cur]
        rec = None
        if len(returned_records) == 0:
            continue
        elif len(returned_records) > 1:
            returned_times = set([ x["lastModifiedTime"] for x in returned_records ])
            if len(returned_times) == 1:
                rec = returned_records[0]
            else:
                sys.stderr.write("geoproc_library.py: Warning: Retrieved multiple records (%d) with different dates (%d) for IP address %s (converted to %d).  Skipping records for this IP.  The records are:\n" % (len(returned_records), len(returned_times), ip, ip_as_int))
                sys.stderr.write("\t%r\n" % returned_records)
        else:
            rec = returned_records[0]
        if rec:
            ip_mappings[ip] = {
              "maxmind_ipv4_time":  rec["lastModifiedTime"],
              "requested_time": ips_date_time,
              "country":       rec["country"],
              "region":        rec["region"],
              "city":          rec["city"],
              "postalCode":    rec["postalCode"],
              "latitude":      rec["latitude"],
              "longitude":     rec["longitude"]
            }
    return ip_mappings

def small_earth_radius_at_latitude(latitude):
    """
    This function gives the radius of the circle that is planar-parallel with the circle of the earth slicing through the equator.
    The value is based on the smallest radius of the Earth (the radius varies between 3947 and 3968 miles [1]).  This error is intentional, to make the bounding-box function using that calls this function err on the large side.

    latitude should be a floating point value in degrees.

    The return value is in miles.

    [1] http://en.wikipedia.org/wiki/Earth_radius
    """
    return math.cos( latitude * math.pi/180 ) * 3947

def latlong_to_bounding_square(latitude, longitude, sidelength):
    """
    Given a latitude, longitude, and side-of-square length, this returns a bounding square with side length @sidelength, centered at (@latitude, @longitude), oriented basically upright (bottom parallel with equator).
    @sidelength should be a floating-point number, meant to be the number of miles desired.
    Return value is a polygon in MySQL Well-Known Text ("WKT") format, or None if something went awry.
    """
    for param in [("latitude", latitude), ("longitude", longitude), ("sidelength", sidelength)]:
        if not (isinstance (param[1], float) or isinstance(param[1], int)):
            sys.stderr.write("Warning: Parameter %s is of invalid type (%r).  Value: %r.\n" % (param[0], type(param[1]), param[1]))
            return None
    #lat_n and lat_s further simplify the model of the earth to be perfectly spherical.  The smallest Earth radius is used to represent the radius at the equator; this increases the proportion fo the great circle at the equator consumed by the sidelength (sidelength measured in miles). Hence this bounding box will err on the large side.
    lat_n = latitude + 360 * sidelength / small_earth_radius_at_latitude(0) 
    lat_s = latitude - 360 * sidelength / small_earth_radius_at_latitude(0) 
    lon_ne = longitude + 360 * sidelength / small_earth_radius_at_latitude(lat_n)
    lon_nw = longitude - 360 * sidelength / small_earth_radius_at_latitude(lat_n)
    lon_se = longitude + 360 * sidelength / small_earth_radius_at_latitude(lat_s)
    lon_sw = longitude - 360 * sidelength / small_earth_radius_at_latitude(lat_s)
    
    #Going in quadrant order: counter-clockwise from NE
    return "POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))" % (
      lat_n, lon_ne,
      lat_n, lon_nw,
      lat_s, lon_sw,
      lat_s, lon_se,
      lat_n, lon_ne
    )

def latlongs_to_networked_locations(mysqlcur, lat, lon, radius):
    """
    Returns None or a list of database dictionary records (plus distance field).
    Records are ordered by distance_miles, ascending.

    Record fields: country, region, city, postalCode, latitude, longitude, distance_miles
    """
    retrecs = []
    if not mysqlcur:
        return None
    else:
        wkt_bounding_box = latlong_to_bounding_square(lat, lon, radius)
        if wkt_bounding_box is None:
            return None
        sql_query = """
          SELECT
            country,
            region,
            city,
            postalCode,
            latitude,
            longitude
          FROM
            LocationTable,
            LocationLatLongs,
            (
              SELECT
                lastModifiedTime
              FROM
                LocationTable
              ORDER BY
                lastModifiedTime DESC
              LIMIT 1
            ) AS lmt
          WHERE
            MBRContains(GeomFromText('""" + wkt_bounding_box + """'), LocationLatLongs.latlong) AND
            LocationLatLongs.lastModifiedTime = lmt.lastModifiedTime AND
            LocationLatLongs.lastModifiedTime = LocationTable.lastModifiedTime AND
            LocationLatLongs.locId = LocationTable.locId
        """
        try:
            mysqlcur.execute(sql_query)
            #Make (distance, record number, record) triples for easy sorting and filtering on distance (tie-breaker the record number).
            rows_for_ordering = [(great_circle_distance(lat, lon, row["latitude"], row["longitude"]), rowno, row) for (rowno, row) in enumerate(mysqlcur)]
            refrows = [row for row in sorted(rows_for_ordering)]
            #dprint("Debug: All networked locations near (%r, %r):\n\t%r\n" % (lat, lon, refrows))
            #Get the nearest city within 30 miles
            for refrow in refrows:
                outrow = refrow[2]
                outrow["distance_miles"] = refrow[0]
                retrecs.append(outrow)
        except:
            sys.stderr.write("Warning: Database query or query results processing failed. Stack trace follows.\n")
            sys.stderr.write(traceback.format_exc())
            return None
        return retrecs


def update_db(connection, cursor, table_name, update_dict, id_field, id, commit):
#TODO This came from RegXML Extractor; instead of copy-pasting, the symbol should just be imported and re-exported.
    if len(update_dict.keys()) > 0:
        sql_update_columns = []
        sql_update_values = []
        for k in update_dict.keys():
            sql_update_columns.append(k)
            sql_update_values.append(update_dict[k])
        sql_update_values.append(id)
        sql_update_statement = "UPDATE " + table_name + " SET " + ", ".join(map(lambda x: x + " = ?", sql_update_columns)) + " WHERE " + id_field + " = ?"
        try:
            cursor.execute(sql_update_statement, tuple(sql_update_values))
        except:
            sys.stderr.write("Failed upate.\nStatement:\t" + sql_update_statement + "\nData:\t" + str(tuple(sql_update_values)) + "\n")
            raise
        if commit:
            connection.commit()

def insert_db(cursor, table_name, update_dict):
#TODO This came from RegXML Extractor; instead of copy-pasting, the symbol should just be imported and re-exported.
    if len(update_dict.keys()) > 0:
        sql_insert_columns = []
        sql_insert_values = []
        for k in update_dict.keys():
            sql_insert_columns.append(k)
            sql_insert_values.append(update_dict[k])
        sql_insert_statement = "INSERT INTO " + table_name + "(" + ",".join(sql_insert_columns) + ") VALUES(" + ",".join("?" * len(sql_insert_columns)) + ");"
        try:
            cursor.execute(sql_insert_statement, tuple(sql_insert_values))
        except:
            sys.stderr.write("Failed insertion.\nStatement:\t" + sql_insert_statement + "\nData:\t" + repr(tuple(sql_insert_values)) + "\n")
            raise

def get_results_dirs(somepath):
    """
    'somepath' is to have directories underneath it that house geoproc results for disk images.
    """
    retlist = []
    if os.path.isdir(somepath):
        for (dirpath, dirnames, filenames) in os.walk(somepath):
            if "verify_disk_image.sh" in dirnames:
                retlist.append(dirpath)
    elif os.path.isfile(somepath):
        with open(somepath, "r") as dirnames:
            for (lineno, line) in enumerate(dirnames):
                cleaned_line = line.strip()
                if os.path.isdir(cleaned_line) and os.path.isfile(os.path.join(cleaned_line, "index.html")):
                    retlist.append(cleaned_line)
                else:
                    sys.stderr.write("Warning: line %d of %r doesn't appear to be a geoproc results directory.\n" % (lineno, args.results))
    return sorted(retlist)

def great_circle_distance(lata, lona, latb, lonb):
    """
    Returns approximate distance in miles from latlonga to latlongb along surface of Earth.
    lata, lona, etc. are expected to be floating point numbers in degrees.
    Great-circle distance is calculated with the Haversine formula.
    Approximation: The Earth's radius is simplified to the equatorial radius. North-south distance estimations will thus err on the large side, since the great-circle distance is proportional to the Earth's radius and our simplification increases the semi-minor axis.
    """
    earth_radius = 3963.190592
    #Python's trig functions work in radians
    lata_radians = lata * math.pi/180
    lona_radians = lona * math.pi/180
    latb_radians = latb * math.pi/180
    lonb_radians = lonb * math.pi/180

    frac1 = (1 - math.cos(latb_radians - lata_radians))/2
    frac2 = (1 - math.cos(lonb_radians - lona_radians))/2
    return 2 * earth_radius * math.asin(math.sqrt(frac1 + math.cos(lata_radians) * math.cos(latb_radians) * frac2))

#Paths c/o SANS Forensics poster, with some tweaks from observed data
rx_web_cache_internetexplorer_winxp = re.compile(r"\/Local Settings\/Temporary Internet Files\/Content.IE5")
rx_web_cache_internetexplorer_win7 = re.compile(r"\/AppData\/Local\/Microsoft\/Windows\/Temporary Internet Files\/(Low\/)?Content.IE5")
rx_web_cache_firefox_winxp = re.compile(r"\/Local Settings\/Application Data\/Mozilla Firefox\/Profiles\/[^\/]{4,16}.default\/Cache")
rx_web_cache_firefox_win7 = re.compile(r"\/AppData\/(Local|Roaming)\/Mozilla Firefox\/Profiles\/[^\/]{4,16}.default\/Cache")
rx_web_cache_firefox_ubuntu = re.compile(r"\.mozilla\/firefox\/[^\/]{4,16}\.default\/Cache")
rx_web_cache_opera_ubuntu = re.compile(r"\.opera\/cache")

def path_in_web_cache(path):
    if path is None:
        return None
    for rx in [
      rx_web_cache_internetexplorer_winxp,
      rx_web_cache_internetexplorer_win7,
      rx_web_cache_firefox_winxp,
      rx_web_cache_firefox_win7,
      rx_web_cache_firefox_ubuntu,
      rx_web_cache_opera_ubuntu
    ]:
      if rx.search(path):
          return True
    return False

rx_aq_email_address = re.compile(r"<(?P<email>.{1,256})>")
rx_webmail_domains = re.compile(r"(hotmail\.com|gmail\.com|yahoo\.com)")

def in_webmail_domain(to_line):
    if to_line is None:
        return None
    email_address = to_line
    #Maybe we can get more specific than the whole line
    angle_quoted_match = rx_aq_email_address.search(to_line)
    if angle_quoted_match:
        email_address = angle_quoted_match.groupdict()["email"]

    address_parts = email_address.split("@")
    if len(address_parts) == 2:
        if rx_webmail_domains.search(address_parts[1].lower()):
            return True
    return False

def connect_to_fs_anno_db(anno_path):
    """
    anno_path: Path to the main output database of verify_fiwalk_versus_tsk_db.
    """
    annoconn = None
    annocur = None
    if anno_path:
        annoconn = sqlite3.connect(anno_path)
        annoconn.row_factory = sqlite3.Row
        annocur = annoconn.cursor()
        tskout_path = os.path.join(os.path.split(anno_path)[0], "tskout.db")
        annocur.execute("ATTACH DATABASE '%s' AS tskout;" % tskout_path)
    return annoconn, annocur

def forensic_path_to_anno_recs(annocur, forensic_path):
    if annocur is None:
        return None
    base_address = int(forensic_path.split("-")[0])
    #Look up file owner by seeing which files contain the beginning byte of the feature
    #Note that multiple files can contain a feature; this coudld be by hard links, de-dupe, finding an unallocated file, etc.
    #(Assumed probability of a feature crossing two _file_ boundaries: Negligible.)
    annocur.execute("""
      SELECT
        tf.*
      FROM
        indexed_tsk_file_layout AS itfl,
        tskout.tsk_files AS tf
      WHERE
        tf.obj_id = itfl.obj_id AND
        itfl.byte_start <= ? AND
        itfl.byte_end >= ?
      ORDER BY
        itfl.byte_start DESC
      ;
    """, (base_address, base_address))
    annorecs = []
    for row in annocur:
        rowdict = { key:row[key] for key in row.keys() }
        #Add fiwalk ID (TODO: this may be more efficiently done later with a join)
        annocur.execute("""
          SELECT
            fiwalk_id
          FROM
            tsk_obj_id_to_fiwalk_id
          WHERE
            tsk_obj_id = ?;
        """, (rowdict["obj_id"],))
        mappingrows = [row for row in annocur]
        if len(mappingrows) > 1:
            sys.stderr.write("Warning: Multiple Fiwalk ID's found for tsk_obj_id %d. Assigning only first.  This may cause strange results.\n" % rowdict["obj_id"])
        if len(mappingrows) > 0:
            rowdict["fiwalk_id"] = mappingrows[0]["fiwalk_id"]
        annorecs.append(rowdict)
    return annorecs

def re_matches_in_text(pattern, line):
    """A generator for searching multiple times in a line.  This is what I wish re.finditer would do, returning Match objects instead of returning only matched text."""
    current_start = 0
    match = pattern.search(line)
    while match:
        yield match
        current_start = match.end()
        match = pattern.search(line, current_start)

def bulk_extractor_ips(beoutdir):
    """
    A generator for the data lines in Bulk Extractor's ip.txt file (the IP addresses extracted from binary structures, not from text).
    """
    if not (os.path.isdir(beoutdir) and os.path.exists(os.path.join(beoutdir, "report.xml"))):
        raise ValueError("Bulk Extractor input is not a BE output directory\n\tParameter: %r." % beoutdir)
    #This BE feature file should not be opened in binary mode
    with open(os.path.join(beoutdir, "ip.txt"), "r") as ip_file:
        for line in ip_file:
            if bulk_extractor_reader.is_comment_line(line):
                continue
            line_parts = line[:-1].split("\t")
            if len(line_parts) != 3:
                raise ValueError("Bulk Extractor ip.txt file has line in unexpected format; halting to await code revisions.\n\tLine with characters escaped: %r." % line)
            yield tuple(line_parts)


if __name__ == "__main__":
    import argparse
    import dfxml
    parser = argparse.ArgumentParser(description="Library meant for inclusion in geoproc scripts. Can be run for regression testing.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug printing (writes to stderr).")
    parser.add_argument("-r", "--regress", action="store_true", help="Run regression tests and exit.")
    args = parser.parse_args()

    if args.regress:
        assert great_circle_distance(1,2,3,4) != 0

        test_wkt = latlong_to_bounding_square(36.0, -122.0, 30)
        if args.debug:
            sys.stderr.write("Debug: test_wkt = %r.\n" % test_wkt)
        assert test_wkt is not None
        test_not_wkt = latlong_to_bounding_square(1, "2", 3)
        assert test_not_wkt is None

        test_match_iter_string = "asdf_asdfasdf"
        test_match_iter_re = re.compile("asdf")
        assert 3 == len([match for match in re_matches_in_text(test_match_iter_re, test_match_iter_string)])

        assert path_in_web_cache(None) is None
        assert path_in_web_cache("/home/foober/.mozilla/firefox/mf74msi2.default/Cache/0/13/F4EF3c01")

        assert in_webmail_domain(None) is None
        assert in_webmail_domain("foo@gmail.com")
        assert in_webmail_domain("foo@yahoo.com")
        assert not in_webmail_domain("foo_hotmail.com")

        assert ip_to_int("1.2.3.4") == 16909060
        assert int_to_ip(16909060) == ("1.2.3.4")
        assert ip_to_int("1.2.3.4.5") is None
        assert ip_to_int("1.2.3") is None

        #Test IP extraction from unstructured text
        ip_string_sets = [
          ("from mail.foo.com (mail.foo.com [164.29.53.12])", set(["164.29.53.12"])),
          ("addr=4,164.29.53.999&version=4.3.2.1.0", set([])),
          ("123.45.67.89.87.999.1.2.3.4.125", set([])),
          ("""from [10.0.1.194]
           (70-91-87-57-BusName-metrodr.md.hfc.comcastbusiness.net. [70.91.87.57]) by
            mx.google.com with ESMTPS id thuap.20.2012.06.26.23.03.08
             (version=SSLv3 cipher=OTHER)""", set(["10.0.1.194", "70.91.87.57"]))
        ]
        for (ipstring, ipset) in ip_string_sets:
            try:
                test_extracted_ips = all_ipv4s(ipstring)
                assert test_extracted_ips == ipset
            except AssertionError as e:
                sys.stderr.write("Error: IP extraction has a difference in results:\n\tTest string: %r\n\tMatched these patterns: %r\n\tMissed these patterns: %r\n\tShouldn't have found these patterns: %r\n" % (
                  ipstring,
                  test_extracted_ips,
                  ipset - test_extracted_ips,
                  test_extracted_ips - ipset
                ))
                raise e
