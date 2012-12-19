#!/usr/bin/env python3

"""
For usage instructions, see the argument parser description below, or run this script without arguments.
"""

__version__ = "0.3.3"

import dfxml,fiwalk
import sys,os,re
import argparse
import collections

#Key: volume offset + ":" + filename
#Value: Dictionary, key: sequence number, value: fileobject gathered during proc_dfxml()
#Why we have this: '.../Thunderbird/Profiles/.../Inbox.msf' indicates a sibling file 'Inbox' (similar for arbitrary names), which is awkward to extract with just the SAX interface.
#The nested dictionary is necessary because of some file paths being ambiguous (they tend to be JS files, but if it happens at all, we should handle the case)
thunderbird_fileobjects = collections.defaultdict(dict)

#Key: Volume offset + ":" + filename
#Value: List of stash paths
thunderbird_paths_to_stash_paths = dict()

def path_matches_thunderbird(path):
    return re.search(r"/(Thunderbird|SeaMonkey)/Profiles/[^/]+/",path, re.I) is not None or re.search(r"/.thunderbird",path, re.I) is not None

def ext_from_path(path):
    components = os.path.splitext(path)
    if "" in components:
        #Infer proper extension from path
        if path_matches_thunderbird(path):
            ext = ".mbox"
        else:
            ext = ""
    else:
        ext = components[1]
    return ext

def dump_fi(fi):
    global imageabspath
    #Set up output file name
    fi_id = fi.tag("id")
    if fi_id is None:
        raise "File object with null ID encountered; should not happen with Fiwalk output."
    outfilename = str(fi_id) + ext_from_path(fi.filename().lower())
    
    #Thunderbird happens to keep an .msf file for containing folders, so check whether we're about to try to dump a directory.
    if fi.is_dir():
        return

    #Dump file
    dump_success = False
    try:
        with open(outfilename, "wb") as outfile:
            outfile.write(fi.contents())
            outfile.close()
            dump_success = True
    except Exception as ex:
        sys.stderr.write(str(ex) + "\n")
    if not dump_success:
        sys.stderr.write("Warning: Extraction failed while writing file %r.\n" % outfilename)
    
    #AJN: We could run extraction utilities here, but instead we're leaving that to the script caller.  This script is about extracting output, not normalizing it.
    
    #Output to manifest only the successfully extracted files.
    #This leaves a little litter in the output directory, as unsuccessfully extracted files may have been partially dumped.
    #TODO It might be worthwhile outputting DFXML here instead of a tab-delimited file.  Subsetting DFXML isn't in dfxml.py as of this script, though, so that'll wait 'til later.
    print("\t".join(map(str, [
      outfilename,
      imageabspath,
      fi.filename()
    ])))

def proc_dfxml(fi):
    global thunderbird_fileobjects

    #For now, we are only matching on file names.  Bail early if fi's unnamed.
    in_partition_path = fi.filename()
    if in_partition_path is None:
        return
    #Also bail if it isn't allocated. We want names and file contents, but just the up-to-date ones.
    #TODO Carved-file processing can come in future work.
    if not fi.allocated():
        return

    basename = os.path.basename(in_partition_path).lower()

    if basename.endswith((".pst", ".mbox", ".dbx")):
        dump_fi(fi)
    elif basename.endswith(".mbs") and re.search(r"/.opera/mail",in_partition_path,re.I) is not None:
        #Opera stores email messages individually as .mbs files, under ~/.opera in Ubuntu 12.04
        dump_fi(fi)
    elif path_matches_thunderbird(in_partition_path):
        #Stash Thunderbird names for file matching
        #Stash path disambiguates multiply-occuring files with the volume offset, path
        #(Sequence identifier found necessary due to Fiwalk v0.6.18, run on M57's Charlie 2009-11-18 image.)
        stash_path = ":".join([
          str(fi.volume.offset),
          in_partition_path
        ])
        seq_number = str(fi.tag("seq"))
        if stash_path in thunderbird_fileobjects and seq_number in thunderbird_fileobjects[stash_path]:
            raise Exception("Stash path of allocated file is not distinct, but it really should be.\n\tstash_path: %r\n\tseq_number: %r\n\tStashed fi id: %r\n\tNew fi id: %r" % (stash_path, seq_number, thunderbird_fileobjects[stash_path].tag("id"), fi.tag("id")))
        thunderbird_fileobjects[stash_path][seq_number] = fi

if __name__=="__main__":
    global imageabspath
    
    parser = argparse.ArgumentParser(description="Find email files in imagefile and dump to files in pwd in the order they're encountered, with a manifest printed to stdout.")
    parser.add_argument("-x", "--xml", dest="dfxml_file_name", help="Already-created DFXML file for imagefile")
    parser.add_argument("-d", "--debug", help="Enable debug output", action="store_true")
    parser.add_argument("imagefilename", help="Image file")
    args = parser.parse_args()
    
    xmlfh = None
    if args.dfxml_file_name != None:
        xmlfh = open(args.dfxml_file_name, "rb")
    imageabspath = os.path.abspath(args.imagefilename)
    
    fiwalk.fiwalk_using_sax(imagefile=open(imageabspath, "rb"), xmlfile=xmlfh, callback=proc_dfxml)
    #Dump thunderbird objects, which require a little path manipulation to get mbox files
    if args.debug:
        sys.stderr.write("Debug: These are the paths found searching for Thunderbird files.\n")
        for stash_path in sorted(thunderbird_fileobjects.keys()):
            sys.stderr.write("\t" + stash_path + "\n")
            for seq_number in sorted(thunderbird_fileobjects[stash_path].keys()):
                sys.stderr.write("\t\t" + seq_number + "\n")
    for stash_path in sorted(thunderbird_fileobjects.keys()):
        if stash_path.endswith(".msf") and stash_path[:-4] in thunderbird_fileobjects:
            dumpee_fi_dict = thunderbird_fileobjects[stash_path[:-4]]
            if len(dumpee_fi_dict) > 1:
                sys.stderr.write("Note: Found multiple Thunderbird email files with the same file system and volume path.  Dumping all.\n\tVolume : path: %r.\n" % stash_path)
            for seq_number in sorted(dumpee_fi_dict.keys()):
                dump_fi(dumpee_fi_dict[seq_number])
