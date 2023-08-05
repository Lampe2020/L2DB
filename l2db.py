#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
The L2DB database format, version 1. (c) Lampe2020 <kontakt@lampe2020.de>
L2DB supports the following data types:
    * keys: string (UTF-8-encoded text)
    * Values: integer (32-bit), long (64-bit), float (32-bit), double (64-bit), string (UTF-8-encoded text), raw (binary data)

####################################################################################
# NOTE that this code doesn't fully comply with the standard defined in SPEC.md! #
####################################################################################
→ This is the case because I changed some things when actually coming up with a spec instead of just randomly creating spaghetti code.
"""

import collections.abc as collections
import struct

#####################################################################
# Helper functions - must be moved into `L2DB.__helpers()` later on #
#####################################################################

def overwrite_in_file(path, offset, data):
    """Overwrite only `len(data)` bytes in file `path` beginning at `offset`"""
    with open(path, 'r+b') as f:
        f.seek(offset)    # Move the file pointer to the desired position
        f.write(data)     # Write the new data, overwriting the existing content at that position
    return data

def getbit(seq, pos):
    """Get only the bit at offset `pos` from the right in number `seq`."""
    return 1&(seq>>pos)

##############
# Exceptions #
##############

class L2DBError(Exception):
    def __init__(self, message=''):
        super().__init__(self.message)

class L2DBVersionMismatch(L2DBError):
    def __init__(self, db_ver='0.0.0', imp_ver='0.0.0'):
        super().__init__(
            f'The database follows the spec version {db_ver} but the implementation follows the spec version {imp_ver}.\
             Conversion failed.'
        )

class L2DBTypeError(L2DBError):
    def __init__(self, keyname='', ktype='inv'): # Renamed `type` to `ktype` because `type` is a Python3-builtin
        toreplace = ("'", "\\'")
        super().__init__(f"Could not convert '{keyname.replace(*toreplace)}' to type '{ktype.replace(*toreplace)}'")

class L2DBKeyError(L2DBError):
    def __init__(self, key=''):
        toreplace = ("'", "\\'")
        super().__init__(f"Key '{key.replace(*toreplace)}' could not be found")

########
# Test #
########

if __name__ == '__main__':
    try:
        db = L2DB({'hello':'world','key':'value','some number':42,'Does bool exist?':True})
        print(f'db =           {db}\ndb.metadata =  {db.metadata}\ndb.__database =  {db._L2DB__database}')
        print(f'db2 =          {(db2:=L2DB(db.syncout_db()))}\ndb2.metadata = {db2.metadata}\ndb2.__database = {db2._L2DB__database}')
    except Exception as e:
        print('''Could unfortunately not demo the database functionality!
The following technical mumbo jumbo should show what went wrong:''')
        from traceback import format_exc as show_last_traceback

        print(show_last_traceback())
