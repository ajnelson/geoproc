#!/usr/bin/env python3

"""
For usage instructions, see the argument parser description below, or run this script without arguments.
"""

__version__ = "0.1.3"

import dfxml,fiwalk
import os,sys,sqlite3,argparse

TSK_FS_META_FLAG_ALLOC = 1 #Drawn from tsk3/fs/tsk_fs.h

def proc_dfxml(fi):
    """
    Map Fiwalk IDs to TSK IDs, for allocated files.
    """
    global outconn,outcur,tskconn,tskcur,TSK_FS_META_FLAG_ALLOC
    fiwalk_id = None
    fiwalk_name = None
    if fi.allocated():
        try:
            fiwalk_id = int(fi.tag("id"))
        except:
            sys.stderr.write("Warning: Could not make integer of Fiwalk ID '%s'.\n" % fi.tag("id"))
        try:
            fiwalk_name = fi.filename()
        except:
            sys.stderr.write("Warning: Could not get filename of Fiwalk ID '%d'.\n" % fiwalk_id)
    #Why this is complicated: Fiwalk assigns the id (<id>) by incrementing a local variable, and TSK assigns the id ("obj_id") with sqlite3's row counter.  Hence it is impossible to join using only the id variable, as they can fall out of sync.
    #   fiwalk_tsk.cpp: file_info("id",next_id++); <---- Grep for this line if you're interested in the source
    #It is impossible to join against TSK's tsk_files.fs_obj_id or .obj_id fields with only this id variable.
    #(The appropriate variable to link against is .obj_id.  fs_obj_id is the containing file system's ID.)
    #In fiwalk_tsk.cpp, fs_file->meta doesn't have access to the counter TSK's using to track unique files.  In db_sqlite.cpp, the file id counter is set in addObject: objId = sqlite3_last_insert_rowid(m_db);
    #We need to join with something else.  Path and file system matching works alright, unless we hit an unallocated entry.  Also, some meta files don't match (TSK calls the data attribute of $Secure "$Secure:$SDS", where Fiwalk just dubs "$Secure".
    
    if not None in [fiwalk_id, fiwalk_name]:
        #Populate fiwalk_id_to_tsk_obj_id and tsk_obj_id_to_fiwalk_id
        tsk_obj_id = None
        tsk_obj_id_maybe_list = []
        #If we need other parent-child obj_id references, see table tsk.tsk_objects
        #Fiwalk records allocation status, but TSK's allocation status needs to be computed from meta_flags.
        for row in outcur.execute("""
          SELECT
            fi.img_offset AS p_img_byte_offset,
            fp.obj_id,
            full_path
          FROM
            tsk.tsk_fs_info AS fi,
            tsk_file_full_paths AS fp
          WHERE
            fi.obj_id = fp.fs_obj_id AND
            file_meta_flags & ? = ? AND
            fi.img_offset = ? AND
            full_path = ?
          ;
          """, ( TSK_FS_META_FLAG_ALLOC, TSK_FS_META_FLAG_ALLOC, fi.volume.offset, "/" + fiwalk_name )):
            tsk_obj_id_maybe_list.append(row["obj_id"])
        if len(tsk_obj_id_maybe_list) == 1:
            tsk_obj_id = tsk_obj_id_maybe_list[0]
        elif len(tsk_obj_id_maybe_list) > 1:
            sys.stderr.write("Warning: fileobject <id>%d</id> found multiple TSK matches: %r.\n" % (fiwalk_id, tsk_obj_id_maybe_list))
        outcur.execute("INSERT INTO fiwalk_id_to_tsk_obj_id(fiwalk_id,tsk_obj_id) VALUES (?,?);", (fiwalk_id, tsk_obj_id))
        outcur.execute("INSERT INTO tsk_obj_id_to_fiwalk_id(fiwalk_id,tsk_obj_id) VALUES (?,?);", (fiwalk_id, tsk_obj_id))

if __name__=="__main__":
    global outconn,outcur,tskconn,tskcur
    
    parser = argparse.ArgumentParser(description="Verify Fiwalk file object ids versus TSK database.  Note we only map allocated entries for now.")
    parser.add_argument("dfxml", help="DFXML file for subject imagefile")
    parser.add_argument("tskdb", help="TSK database for subject imagefile")
    parser.add_argument("outdb", help="Output database, must not exist")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stdout")
    args = parser.parse_args()
    
    #Set up output database
    if os.path.exists(args.outdb):
        raise Exception("Output database must not exist.")
        sys.exit(1)
    outconn = sqlite3.connect(args.outdb)
    outconn.isolation_level = "EXCLUSIVE"
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()

    #Set up input database
    tskconn = sqlite3.connect(args.tskdb)
    tskconn.isolation_level = None
    tskconn.row_factory = sqlite3.Row
    tskcur = tskconn.cursor()

    outcur.execute("ATTACH DATABASE '%s' AS tsk;" % args.tskdb)
    if args.verbose:
        sys.stdout.write("Creating full path table...")
    outcur.execute("""
        CREATE TABLE tsk_file_full_paths AS
        SELECT
          fs_obj_id,
          obj_id,
          meta_flags AS file_meta_flags,
          parent_path || name AS full_path
        FROM
          tsk.tsk_files
        ORDER BY
          full_path
        ;
        """)
    if args.verbose:
        sys.stdout.write("Done.\n")
        sys.stdout.write("Creating index on paths...")
    outcur.execute("CREATE INDEX fullPath on tsk_file_full_paths(full_path);")
    if args.verbose:
        sys.stdout.write("Done.\n")
        sys.stdout.write("Creating and populating mapping table and index...")
    outcur.execute("CREATE TABLE fiwalk_id_to_tsk_obj_id (fiwalk_id NUMBER PRIMARY KEY, tsk_obj_id NUMBER);")
    outcur.execute("CREATE INDEX fiwalkId ON fiwalk_id_to_tsk_obj_id(fiwalk_id);")
    #TODO The tsk_obj_id:fiwalk_id mapping is commonly many-to-one. Need to figure out how to resolve this.
    outcur.execute("CREATE TABLE tsk_obj_id_to_fiwalk_id (tsk_obj_id NUMBER, fiwalk_id NUMBER);")
    outcur.execute("CREATE INDEX tskObjId ON tsk_obj_id_to_fiwalk_id(tsk_obj_id);")
    if args.verbose:
        sys.stdout.write("Done.\n")
        sys.stdout.write("Creating copy of byte-runs-esque table for indexing...")
    #There isn't currently an index for the byte runs in TSK.
    outcur.execute("""
      CREATE TABLE indexed_tsk_file_layout AS
      SELECT
        *,
        byte_start + byte_len AS byte_end
      FROM
        tsk.tsk_file_layout
      ORDER BY
        byte_start, byte_end, obj_id;
    """)
    outcur.execute("CREATE INDEX itfl_start ON indexed_tsk_file_layout(byte_start);")
    outcur.execute("CREATE INDEX itfl_end ON indexed_tsk_file_layout(byte_end);")
    if args.verbose:
        sys.stdout.write("Done.\n")
    sys.stdout.flush()

    #Process DFXML
    with open(args.dfxml, "rb") as xmlfh:
        fiwalk.fiwalk_using_sax(xmlfile=xmlfh, callback=proc_dfxml)
    if args.verbose:
        sys.stdout.write("Done.\n")

    #Cleanup
    outconn.commit()
    outcur.execute("DETACH DATABASE tsk;")
    outcur.close()
    tskcur.close()
