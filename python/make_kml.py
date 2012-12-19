#!/usr/bin/env python3
"""
make_kml.py: Produce aggregate KML report
"""

__version__ = "0.2.5"

import sys
import os
import argparse
import sqlite3
import collections

import success
import geoproc_library

TABLE_SCRIPT_DB = [
  ("cookie_files_votes", "analyze_cookie_files.sh", "cookie_files_votes.db"),
  ("email_files_votes", "analyze_email_files.sh", "email_files_votes.db"),
  ("exif_headers_votes", "analyze_exif_headers.sh", "exif_headers_votes.db")
]

kml_head = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Image Locations</name>
    <!--KML pushpin stylings taken from Google Earth sample output and amped up  (scale 1.1 to 10.1) for global visibility-->
    <Style id="s_red-pushpin">
      <IconStyle>
        <scale>10.1</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png</href>
        </Icon>
        <hotSpot x="20" y="2" xunits="pixels" yunits="pixels"/>
      </IconStyle>
    </Style>
    <StyleMap id="m_red-pushpin">
      <Pair>
        <key>normal</key>
        <styleUrl>#s_red-pushpin</styleUrl>
      </Pair>
      <Pair>
        <key>highlight</key>
        <styleUrl>#s_red-pushpin_hl</styleUrl>
      </Pair>
    </StyleMap>
    <Style id="s_red-pushpin_hl">
      <IconStyle>
        <scale>10.1</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png</href>
        </Icon>
        <hotSpot x="20" y="2" xunits="pixels" yunits="pixels"/>
      </IconStyle>
    </Style>
"""
kml_foot = """  </Document>
</kml>"""
kml_placemark = """<Placemark>
    <name>%s</name>
    <description>%s</description>
    <Point>
      <coordinates>%s,%s,0 </coordinates>
    </Point>
  </Placemark>"""

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

def dict_to_dl(somedict, orderlist=None):
    if orderlist is None:
        fields = sorted(somedict.keys())
    else:
        fields = orderlist
    retlist = ["<dl>"]
    for field in fields:
        if somedict.get(field) is None:
            continue
        retlist.append("<dt>%s</dt><dd>%s</dd>" % (field, somedict[field]))
    retlist.append("</dl>")
    return "\n".join(retlist)

def main():
    global args

    #To keep down on placemarker clutter, gather information by distinct lat/long.
    #Key: (lat,long) floats.
    #Value: List of records.
    latlong_dict = collections.defaultdict(list)

    
    annoconn = None
    annocur = None
    if args.fs_anno_dir:
        annoconn, annocur = geoproc_library.connect_to_fs_anno_db(os.path.join(args.fs_anno_dir, "tsk_fiwalk_anno.db"))

    for (table, script, dbfile) in TABLE_SCRIPT_DB:
        if args.__dict__.get(table):
            conn = sqlite3.connect(args.__dict__[table])
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            #Get votes
            if args.precision_db:
                dprint("Debug: Joining precision data.")
                cur.execute("ATTACH DATABASE '%s' AS precision;" % args.precision_db)
                #Build join clause by getting columns from vectors table
                cur.execute("SELECT * FROM precision." + table + "_precision_vectors;")
                rows = [row for row in cur]
                fields = rows[0].keys()
                join_clause = " AND ".join(["p." + field + " IS v." + field for field in fields])

                sql_query = "SELECT * FROM %s as v LEFT JOIN precision.%s_precision as p ON %s;" % (table, table, join_clause)
                dprint("Debug: Query with precision is: %r." % sql_query)
                cur.execute(sql_query)
            else:
                #No precision information available
                dprint("Debug: Not joining precision data.")
                cur.execute("SELECT * FROM %s as v;" % table)

            #Convert records to expected dictionary-list format
            for rawrow in cur:
                row = {key:rawrow[key] for key in rawrow.keys()}
                if not (row.get("latitude") and row.get("longitude")):
                    continue
                row["source_table"] = table
                latlong_dict[(row["latitude"], row["longitude"])].append(row)

            #Clean up connections
            if args.precision_db:
                cur.execute("DETACH DATABASE precision;")
            conn.close()
    
    if len(latlong_dict) == 0:
        dprint("Debug: Found nothing to report.")
        sys.exit(0)

    print(kml_head)

    #TODO Take one pass over the whole latlong_dict and sort the records
    #for (latitude,longitude) in latlong_dict:
    #    rows_to_sort = []
    #    for row in latlong_dict[(latitude,longitude)]:
    #        loc_ranker = row.get("p_correct_location")
    #        if loc_ranker is None:
    #            loc_ranker = -1.0
    #        rows_to_sort.append( (loc_ranker, row) )
    #    rows_sorted = sorted(rows_to_sort, reverse=True)
    #    best_row = latlong_dict[(latitude,longitude)][0]

    for (latitude,longitude) in latlong_dict:
        #Determine marker name
        #For now: Just city, by popularity histogram
        #TODO Add believed precision
        name_triples = collections.defaultdict(lambda: 0)
        for row in latlong_dict[(latitude,longitude)]:
            #None is sometimes a legitimate value; dict.get just substitutes on a missing key.
            name_triples[(row.get("country") or " (no country)", row.get("region") or " (no region)", row.get("city") or " (no city)")] += 1
        names_votes = sorted([ (name_triples[k], k) for k in name_triples.keys() ])
        #dprint("Debug: names_votes = %r." % names_votes)
        placemark_name = ", ".join(names_votes[0][1])

        placemark_description_list = []
        placemark_description_list.append("<dl>")
        placemark_description_list.append("<dt>Latitude, longitude</dt>")
        placemark_description_list.append("<dd>%f, %f</dd>" % (latitude, longitude))

        placemark_description_list.append("<dt>Number of artifacts indicating this location</dt>")
        placemark_description_list.append("<dd>%d</dd>" % len(latlong_dict[(latitude,longitude)]))

        #Add to description: Other location names, if any
        if len(names_votes) > 1:
            placemark_description_list.append("<dt>Other location names</dt>")
            placemark_description_list.append("<dd><table>")
            placemark_description_list.append("  <thead><tr><th>Name</th><th>Number of occurrences</th></tr></thead>")
            placemark_description_list.append("  <tfoot></tfoot>")
            placemark_description_list.append("  <tbody>")
            for (tally, name) in names_votes:
                placemark_description_list.append("<tr><td>%s</td>%d<td></td></tr>" % (name, tally))
            placemark_description_list.append("  </tbody>")
            placemark_description_list.append("</table></dd>")

        placemark_description_list.append("</dl>")
        #Add to description: List of files whose contents support this artifact
        if annocur:
            placemark_description_list.append("<table><caption>Supporting artifacts found on the disk, ordered by location precision</caption>")
            placemark_description_list.append("""
<thead>
  <tr>
    <th rowspan="3">TSK fs_obj_id</th>
    <th rowspan="3">TSK obj_id</th>
    <th rowspan="3">Fiwalk id</th>
    <th rowspan="3">Forensic path</th>
    <th rowspan="3">File path</th>
    <th rowspan="3">Within-file record number</th>
    <th colspan="8">Weighted precision: Correct / Number of assertions</th>
  </tr>
  <tr>
    <th colspan="2">Location</th>
    <th colspan="2">Country</th>
    <th colspan="2">Region</th>
    <th colspan="2">City</th>
  </tr>
  <tr>
    <th>%</th>
    <th>C/N</th>
    <th>%</th>
    <th>C/N</th>
    <th>%</th>
    <th>C/N</th>
    <th>%</th>
    <th>C/N</th>
  </tr>
</thead><tfoot></tfoot><tbody>""")
            for row in latlong_dict[(latitude,longitude)]:
                placemark_description_list.append("<tr>")
                placemark_description_list.append("<td>%s</td>" % str(row.get("fs_obj_id", "")))
                placemark_description_list.append("<td>%s</td>" % str(row.get("obj_id", "")))
                placemark_description_list.append("<td>%s</td>" % str(row.get("fiwalk_id", "")))
                placemark_description_list.append("<td>%s</td>" % str(row.get("forensic_path", "")))

                if args.anonymize:
                    placemark_description_list.append("<td>(redacted)</td>")
                elif annocur is None:
                    placemark_description_list.append("<td>(data unavailable)</td>")
                else:
                    annorows = []
                    if row.get("fs_obj_id") and row.get("obj_id"):
                        try:
                            annocur.execute("SELECT full_path FROM tsk_file_full_paths WHERE obj_id = ? AND fs_obj_id = ?;", (row["obj_id"], row["fs_obj_id"]))
                        except TypeError:
                            dprint(repr(row))
                            raise
                        annorows = [row for row in annocur]
                    elif row.get("fiwalk_id"):
                        annocur.execute("""
                          SELECT
                            full_path
                          FROM
                            tsk_file_full_paths as fp,
                            fiwalk_id_to_tsk_obj_id as ftt
                          WHERE
                            fp.obj_id = ftt.tsk_obj_id AND
                            ftt.fiwalk_id = ?;
                        """, (row["fiwalk_id"],))
                        annorows = [row for row in annocur]

                    if len(annorows) != 1:
                        placemark_description_list.append("<td>(not found)</td>")
                    else:
                        placemark_description_list.append("<td>%s</td>" % annorows[0]["full_path"]) #TODO HTML-escape this string

                #The within-file record is formatted differently depending on the artifact type
                within_file_path = ""
                if row["source_table"] == "email_files_votes":
                    if row["message_index"] is not None:
                        within_file_path = "Message %d, " % (row["message_index"] + 1)
                    within_file_path += "<tt>Received</tt> header %d of %d" % (row["received_path_index"] + 1, row["received_path_length"])
                placemark_description_list.append("<td>%s</td>" % within_file_path)

                #Add precision
                for locfield in ["location", "country", "region", "city"]:
                    pcl = row.get("p_correct_" + locfield)
                    ncl = row.get("n_correct_" + locfield)
                    ntl = row.get("n_total_" + locfield)
                    if None in (pcl, ncl, ntl):
                        placemark_description_list.append("<td></td><td></td>")
                    else:
                        placemark_description_list.append("<td>%s</td>" % lite_float_string(100 * pcl))
                        placemark_description_list.append("<td>%s / %s</td>" % (lite_float_string(row["n_correct_" + locfield]), lite_float_string(row["n_total_" + locfield])))

                placemark_description_list.append("</tr>")
            placemark_description_list.append("</tbody></table>")

        placemark_description = "\n".join(placemark_description_list)

        print(kml_placemark % (
          placemark_name,
          placemark_description,
          longitude,
          latitude
        ))

    print(kml_foot)

def lite_float_string(f):
    """
    Lite float formatting c/o reasonable answer at http://stackoverflow.com/a/2440786/1207160
    """
    return ("%f" % f).rstrip("0").rstrip(".")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Produce KML from GeoProc analysis SQLite files.  Writes to stdout.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug messages (writes to stderr).")
    parser.add_argument("-r", "--regress", action="store_true", help="Run regression tests and exit.")

    #Run regression tests
    args_regress = parser.parse_known_args()[0]
    if args_regress.regress:
        test_parser = argparse.ArgumentParser(description="Test parser")
        test_parser.add_argument("--foo")
        test_args = test_parser.parse_args(["--foo", "bar"])
        assert test_args.foo == "bar"
        #Test direct manipulation of args namespace (this saves some code duplication while normalizing arguments)
        test_args.__dict__["baz"] = 2
        assert test_args.baz == 2
        sys.exit(0)

    parser.add_argument("--process_dir", help="Use this GeoProc output directory to find all SQLite files, including votes and file system annotations.  If another *_votes argument is passed, that argument will override.")
    parser.add_argument("--cookie_files_votes", help="Use this SQLite file for cookie file records.")
    parser.add_argument("--email_files_votes", help="Use this SQLite file for email file records.")
    parser.add_argument("--exif_headers_votes", help="Use this SQLite file for EXIF records.")
    parser.add_argument("--fs_anno_dir", help="Directory containing the output of 'verify_fiwalk_versus_tsk_db.sh' output.")

    parser.add_argument("-a", "--anonymize", action="store_true", help="Do not print file system entries.")

    parser.add_argument("-p", "--precision_db", dest="precision_db", help="Database of precision for feature types.")

    args = parser.parse_args()

    if args.process_dir:
        dprint("Debug: Getting results databases from process_dir argument.")
        results_dir_list = geoproc_library.get_results_dirs(args.process_dir)
        if len(results_dir_list) != 1:
            sys.stderr.write("Error: --process_dir argument is not a singular GeoProc output directory.\n")
            sys.exit(1)
        #Do an extra test for TSK anno
        if not args.__dict__.get("fs_anno_dir"):
            if success.success(os.path.join(args.process_dir, "verify_fiwalk_versus_tsk_db.sh.status.log")):
                args.__dict__["fs_anno_dir"] = os.path.join(args.process_dir, "verify_fiwalk_versus_tsk_db.sh")

        for (args_param, analysis_dir, analysis_db) in TABLE_SCRIPT_DB:
            dprint("Debug: Testing %r." % ((args_param, analysis_dir, analysis_db),))
            if args.__dict__.get(args_param):
                dprint("Argument already present.")
                continue
            status_log_path = os.path.join(args.process_dir, analysis_dir + ".status.log")
            if not success.success(status_log_path):
                dprint("Not successful (checked %r.)." % status_log_path)
                continue 
            args.__dict__[args_param] = os.path.join(args.process_dir, analysis_dir, analysis_db)

    infiles = set([
      args.cookie_files_votes,
      args.email_files_votes,
      args.exif_headers_votes
    ])
    if infiles == set([None]):
        parser.error("You must provide at least one input database file to make a map.")
        sys.exit(11)

    main()

