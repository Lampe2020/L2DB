#!/usr/bin/env python3
# -*- coding: utf-8 -*-

spec_version = '1.1.0'
implementation_version = '0.1.0-pre-alpha+python3-above-.7'

__doc__ = f"""
L2DB {spec_version} - implementation {implementation_version}   
Both version numbers follow the SemVer 2.0.0 standard (http://semver.org/spec/v2.0.0.html)   
   
Simple binary database format made by Christian Lampe <kontakt@lampe2020.de>   
   
Spec: see SPEC.md   
This module is the Python3-based example implementation of the database format, feel free to make a better 
implementation.   
This implementation is a strict implementation, so it follows even the rules for strict implementations.   
"""

import collections.abc as collections
import struct, warnings, semver

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
    """L2DB base exception"""
    def __init__(self, message=''):
        self.message = message
        super().__init__(self.message)

class L2DBVersionMismatch(L2DBError):
    """Raised when conversion between spec versions fails"""
    def __init__(self, db_ver='0.0.0-please+replace', imp_ver=implementation_version):
        self.message = f'database follows spec version {db_ver} but implementation follows spec version {imp_ver}. Conversion failed.'
        super().__init__(self.message)

class L2DBTypeError(L2DBError):
    """Raised when conversion between value types fails"""
    def __init__(self, key='', vtype='inv'): # Renamed `type` to `vtype` because `type` is a Python3-builtin
        toreplace = ("'", "\\'")
        self.message = f"Could not convert key '{key.replace(*toreplace)}' to type '{vtype.replace(*toreplace)}'" if (
                key!=None) else f"Could not convert value to type '{vtype.replace(*toreplace)}'"
        super().__init__(self.message)

class L2DBKeyError(L2DBError):
    """Raised when an unaccessible key is accessed"""
    def __init__(self, key=''):
        toreplace = ("'", "\\'")
        self.message = f"Key '{key.replace(*toreplace)}' could not be found"
        super().__init__(self.message)

########
# L2DB #
########

class L2DB:
    __doc__ = f'L2DB {spec_version} in implementation {implementation_version}'
    spec = spec_version
    implementation = implementation_version
    def __init__(self, source, mode, runtime_flags):
        self.__db = {}
        self.source, self.mode, self.runtime_flags = source, mode, runtime_flags
        self.open(source, mode, runtime_flags)

    def open(self, source, mode='rw', runtime_flags=()):
        """Populates the L2DB with new content and sets its source location if applicable.
        Accepts modes 'r', 'w', 'f' and any combination of those three."""

    def read(self, key, vtype=None):
        """Returns the value of the key, optionally converts it to `vtype`.
        Raises an L2DBKeyError if the key is not found.
        Raises an L2DBTypeError if the value cannot be converted to the specified `vtype`."""

    def write(self, key, value, vtype=None):
        """Writes `value` to `key`, optionally converts it to `vtype`.
        Raises an L2DBKeyError if the key name is invalid.
        Raises an L2DBTypeError if the value cannot be converted to the specified `vtype`."""

    def delete(self, key):
        """Removes a key from the L2DB."""

    def convert(self, key, vtype, fromval):
        """Converts the key or value to type `vtype`."""

    def dump(self):
        """Dumps all key-value pairs as a `dict`"""

    def flush(self, file=None, move=False):
        """Flushes the buffered changes to the file the database has been initialized with.
        If a file is specified this flushes the changes to that file instead and changes the database source to the new
        file if `move` is True.
        Raises a FileNotFoundError with the message 'No file specified' if the database has no source file and none is
        specified."""

    def cleanup(self, only_flag=False, dont_rescue=False):
        """Tries to repair the database and unsets the `DIRTY` flag.
        Skips all repairs if `only_flag` is True.
        Discards corrupted key-value pairs instead of rescuing them if `dont_rescue` is True."""

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
