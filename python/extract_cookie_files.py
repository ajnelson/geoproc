#!/usr/bin/env python3

"""
For usage instructions, see the argument parser description below, or run this script without arguments.
"""

#TODO Do the Thunderbird-style pattern-matching extraction for any directory that's named Cookies or similar, and has index.dat; i.e. Cookies/index.dat
#Example data: linuxleo-ntfs_pract.E01; root-level directory "Cookies".

__version__ = "0.1.0"

import dfxml,fiwalk
import sys,os,datetime
import argparse

def proc_dfxml(fi):
    global imageabspath
    global args
    fn = fi.filename()
    if fn is None:
        #All the matching happens on file name for now; might be possible to match some SQLite files by schema later.
        return
    lowfn = fn.lower()
    lowbn = os.path.basename(lowfn)
    lowext = None
    try:
        lowext = os.path.splitext(lowbn)[1]
    except:
        pass
    if (lowfn.find("/cookies/") > -1 and lowext in [".txt",".dat"]) or lowbn == 'cookies.sqlite':
        #Set up output file name
        outfilename = fi.tag("id")
        if not lowext is None:
            outfilename += lowext
        #Dump file
        dump_success = False
        try:
            with open(outfilename, "wb") as outfile:
                if args.debug:
                    sys.stderr.write("Debug: Writing %d bytes to '%s'.\n" % (fi.filesize(), outfilename))
                outfile.write(fi.contents())
                outfile.close()
                dump_success = True
        except Exception as ex:
            sys.stderr.write(str(ex))
            sys.stderr.write('\n')
        if dump_success:
            print(outfilename)
            #TODO delete output that failed to be dumped
            pass

if __name__=="__main__":
    global imageabspath
    global args
    
    parser = argparse.ArgumentParser(description="Find cookie files in imagefile and dump to files in pwd, named by fiwalk id number.")
    parser.add_argument("-x", "--xml", dest="dfxml_file_name", help="Already-created DFXML file for imagefile.")
    parser.add_argument("-d", "--debug", help="Enable debug output.", action="store_true")
    parser.add_argument("imagefilename", help="Image file.")
    args = parser.parse_args()
    
    xmlfh = None
    if args.dfxml_file_name != None:
        xmlfh = open(args.dfxml_file_name, "rb")
    imageabspath = os.path.abspath(args.imagefilename)
    
    fiwalk.fiwalk_using_sax(imagefile=open(imageabspath, "rb"), xmlfile=xmlfh, callback=proc_dfxml)
