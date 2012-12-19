#!/usr/bin/env python3
"""
If called by a shell script, this script has a return status similar in semantics to the 'test' command.
"""

__version__ = "0.1.1"

import sys,os

def success(path):
    """
    Returns True on finding satisfactory completion contents of the supplied path, False otherwise.
    The supplied path should be of a .status.log file.
    """
    retval = False
    if os.path.isfile(path):
        infile = open(path, "r")
        status = infile.read(8).strip()
        if status in ["0", "imported"]:
            retval = True
        infile.close()
    return retval

if __name__ == "__main__":
    rc = success(sys.argv[1])
    sys.exit(0 if rc else 1)
