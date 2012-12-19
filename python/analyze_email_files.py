#!/usr/bin/env python3

__version__ = "0.4.0"

import os
import sys
import argparse
import sqlite3
import collections
import traceback

import geoproc_library
import geoproc_cfg
import dfxml

import email
import mailbox

SQL_CREATE_EMAIL_FILES_VOTES = """CREATE TABLE email_files_votes (
  forensic_path TEXT,
  fiwalk_id NUMBER,
  fs_obj_id NUMBER,
  obj_id NUMBER,
  message_index NUMBER,
  ipv4 TEXT,
  network_proxy_software_detected BOOLEAN,
  believed_timestamp TEXT,
  received_header_text TEXT,
  received_path_index NUMBER,
  received_path_length NUMBER,
  sole_recipient_domain_is_webmail BOOLEAN,
  maxmind_ipv4_time TEXT,
  country TEXT,
  region TEXT,
  city TEXT,
  postalCode TEXT,
  latitude NUMBER,
  longitude NUMBER,
  database_queried BOOLEAN,
  ipv4_be_notes TEXT,
  ipv4_be_has_cksum_or_socket BOOLEAN
);"""

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s) + "\n")

def emails_in_dir_manifest(manifest):
    """
    generator - yields all email _messages_ listed in manifest file.  Individual messages are extracted from mailbox files.
    The yielded item is a triple, (id, seq, em):
      id:  The Fiwalk-assigned ID of the file (encoded as the file's name)
      seq: The sequence index (an mbox can have many emails)
      em:  The email message object (mailbox.mboxMessage or email.message.Message).
    """
    with open(manifest, "r") as manifest_fh:
        #Assumed format: Tab-delimited, field 1 is absolute path to file in processing environment
        for (lineno, line) in enumerate(manifest_fh):
            #Clean and check input
            cleaned_line = line.strip()
            if cleaned_line == "":
                continue
            fn = cleaned_line.split("\t")[0]
            assert os.path.isabs(fn) #We are assuming absolute paths in this manifest
            if not os.path.isfile(fn):
                if not (os.path.isdir(fn) and fn.lower().endswith('readpst')):
                    raise ValueError("Error: Manifest listed a non-file, non-readpst entry; assuming input is corrupt and aborting.\n\tManifest: %s\n\tLine: %d" % (manifest, lineno+1))

            fiwalk_id = int(os.path.basename(fn).split(".")[0])
            #TODO Determine interface for getting file metadata from listing
            #if fiwalk_id not in fiwalk_id_to_path:
            #    sys.stderr.write("Warning: Fiwalk ID (%r) not found in given file system listing." % fiwalk_id)

            #Process listed entries
            dprint("Debug: Checking to see if we know how to process %r." % fn)
            if fn.lower().endswith('mbs'):
                dprint("Debug: Applying mbs rule.")
                with open(fn) as single_email_fh:
                    yield (fiwalk_id, 0, email.message_from_file(single_email_fh))
            elif fn.lower().endswith('mbox'):
                dprint("Debug: Applying mbox rule.")
                for (messageno, message) in enumerate(mailbox.mbox(fn)):
                    yield (fiwalk_id, messageno, message)
            elif fn.lower().endswith('readpst'):
                dprint("Debug: Applying readpst rule.")
                for (dirpath, dirnames, filenames) in os.walk(fn):
                    for filename in filenames:
                        for (messageno, message) in enumerate(mailbox.mbox(os.path.join(dirpath,filename))):
                            yield (fiwalk_id, messageno, message)
            else:
                sys.stderr.write("Warning: Manifest listed a file extension this script doesn't process yet (line %d).\n" % lineno)

def main():
    global args

    #Set up lookup database connection
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

    #Connect to annodb
    annoconn, annocur = geoproc_library.connect_to_fs_anno_db(args.annodb)

    #Verify input
    manifest_path = os.path.join(args.emaildir, "manifest.txt")
    if not os.path.isfile(manifest_path):
        raise Exception("Error: manifest.txt not found in input directory.")

    #Ingest BE ips, if available
    #Stash in (once-tested) histogram.
    #Dictionary key: ipv4 address
    #Dictionary value: (notes, tally) default dictionary.
    ip_notes_histogram = collections.defaultdict(lambda: collections.defaultdict(lambda: 0))
    if args.bulk_extractor_output:
        for (forensic_path, ipv4, ipv4_notes) in geoproc_library.bulk_extractor_ips(args.bulk_extractor_output):
            ip_notes_histogram[ipv4][ipv4_notes] += 1
    dprint("Debug: Number of IPv4s with notes: %d." % len(ip_notes_histogram.keys()))

    #Set up output database
    outdbpath = os.path.join(args.outdir, "email_files_votes.db")
    if os.path.isfile(outdbpath):
        raise Exception("Error: Output database already exists. This script won't overwrite. Aborting.")
    outconn = sqlite3.connect(outdbpath)
    outconn.isolation_level = "EXCLUSIVE"
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()
    outcur.execute(SQL_CREATE_EMAIL_FILES_VOTES)

    for (fiwalk_id, messageno, message) in emails_in_dir_manifest(manifest_path):
        dprint("Debug: Analyzing a record from fiwalk_id %r." % fiwalk_id)
        #print(repr(type(message)))
        #for i in message.keys():
        #    print('%r: %r' % (i, message.get_all(i)))
        received_recs = message.get_all("Received")
        if not received_recs:
            continue
        pathlength = len(received_recs)
        for (pathindex, pathline) in enumerate(received_recs):
            #TODO Just getting all the IPs for now; filter later
            ips = geoproc_library.all_ipv4s(pathline)
            dprint("Debug: Found this many IP's: %d.\n\t%r" % (len(ips), ips))
            
            #Can we get a date?
            maybe_timestamp = None
            maybe_timestamp_match = dfxml.rx_rfc822datetime.search(pathline)
            if maybe_timestamp_match:
                thestring = maybe_timestamp_match.string
                thespan = maybe_timestamp_match.span()
                thedatestring = thestring[thespan[0]:thespan[1]]
                try:
                    maybe_timestamp = dfxml.dftime(thedatestring)
                except:
                    sys.stderr.write("Warning: An error occured trying to parse time input.\nInput:%r\nStack trace:\n" % thedatestring)
                    sys.stderr.write(traceback.format_exc())
                    sys.stderr.write("\n")
                    #Don't stop here.
            dprint("Debug: Believed timestamp: %r." % maybe_timestamp)
            
            #Now that we have a date, can we get locations?
            if maybe_timestamp:

                #Can we get a single recipient?  (This is, of course, not guaranteed to be the owner.)
                sole_recipient = None
                delivered_to_headers = message.get_all("Delivered-To")
                to_headers = message.get_all("To")
                if delivered_to_headers and len(delivered_to_headers) == 1:
                    sole_recipient = delivered_to_headers[0]
                elif to_headers and len(to_headers) == 1 and len(to_headers[0].split("\n")) == 1:
                    sole_recipient = to_headers[0]
                all_ip_locations = geoproc_library.ips_to_locations(lookupcur, maybe_timestamp.datetime(), ips)
                dprint("Debug: Fetched these IP location records:\n\t%r" % all_ip_locations)
                for ip in ips:
                    outdict = {"fiwalk_id":fiwalk_id}
                    #TODO Use annodb to get TSK identifiers
                    outdict["message_index"] = messageno
                    outdict["ipv4"] = ip
                    outdict["received_path_index"] = pathindex
                    outdict["received_path_length"] = pathlength
                    outdict["received_header_text"] = pathline
                    outdict["database_queried"] = all_ip_locations is not None
                    outdict["believed_timestamp"] = str(maybe_timestamp)
                    outdict["sole_recipient_domain_is_webmail"] = geoproc_library.in_webmail_domain(sole_recipient)
                    if all_ip_locations is not None and ip in all_ip_locations:
                        rec = all_ip_locations[ip]
                        outdict["latitude"] = rec.get("latitude")
                        outdict["longitude"] = rec.get("longitude")
                        outdict["postalCode"] = rec.get("postalCode")
                        outdict["maxmind_ipv4_time"] = dfxml.dftime(rec.get("maxmind_ipv4_time")).iso8601()
                        if rec.get("country"):
                            outdict["country"] = rec["country"]
                        if rec.get("region"):
                            outdict["region"] = rec["region"]
                        if rec.get("city"):
                            outdict["city"] = rec["city"]
                        dprint("Debug: Checking for IP notes for %r." % ip)
                        if ip in ip_notes_histogram:
                            dprint("Debug: Formatting notes for %r." % ip)
                            notedict = ip_notes_histogram[ip]
                            notelist = sorted(notedict.keys())
                            notes_to_format = []
                            for note in notelist:
                                notes_to_format.append("%d %r" % (notedict[note], note))
                            outdict["ipv4_be_notes"] = "; ".join(notes_to_format)
                            outdict["ipv4_be_has_cksum_or_socket"] = "sockaddr" in outdict["ipv4_be_notes"] or "cksum-ok" in outdict["ipv4_be_notes"]
                        dprint("Debug: Outdict just before inserting:\n\t%r" % outdict)
                    geoproc_library.insert_db(outcur, "email_files_votes", outdict)
    outconn.commit()
    dprint("Debug: Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze email files for geographic artifacts.")
    parser.add_argument("-d", "--debug", help="Enable debug output", action="store_true")
    parser.add_argument("-a", "--annodb", dest="annodb", help="Annotation database.")
    parser.add_argument("-b", "--bulk_extractor_output", help="Bulk Extractor output directory.")
    parser.add_argument("emaildir", help="Input directory containing individual email files (.mbox, .eml, .mbs); assumed to contain 'manifest.txt' listing all successfully-extracted files.")
    parser.add_argument("outdir", help="Output directory.")
    args = parser.parse_args()

    main()
