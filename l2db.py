#!/usr/bin/env python3
# -*- coding: utf-8 -*-

spec_version = '1.1.2'
implementation_version = '0.3.1-pre-alpha+python3-above-.7'

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
NaN = float('nan') # Somehow has no number literal, can only be gotten through a float of the string 'nan'.

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

#TODO: implement this, as dict of names with type prefixes with the values in binary form (bytes object, b'')

class L2DB:
    __doc__ = f'L2DB {spec_version} in implementation {implementation_version}'
    spec = spec_version
    implementation = implementation_version
    def __init__(self, source, mode='rw', runtime_flags=()):
        self.__db = {}
        self.source, self.mode, self.runtime_flags = source, mode, runtime_flags
        self.open(source, mode, runtime_flags)

    def __helpers(self, which=()):
        """Returns the helper functions for internal use.
        As an argument, supply either a tuple with the string names of the specific functions you need
        or an empty tuple to get all.
        If a non-existing function is requested a KeyError will be raised. """
        import struct
        def num2bin(n=0, unsigned=False):
            if n==NaN:
                warnings.warn('L2DB helper num2bin(n): cannot store NaN')
                return b''
            match str(type(n)):
                case 'int':
                    if unsigned: # Requested to be represented as unsigned
                        if n<0: # Must pe represented as signed
                            warnings.warn(f"L2DB helper num2bin(n): unsigned numbers cannot be less than zero")
                            return b''
                        elif n<256: # Can be represented as char
                            return struct.pack('>B', n)
                        elif n<65536: # Can be represented as short
                            return struct.pack('>H', n)
                        elif n<4294967296: # Can be represented as int
                            return struct.pack('>I', n)
                        elif n<18446744073709551616: # Can be represented as long long
                            return struct.pack('>Q', n)
                        else:
                            ll = 18446744073709551615 # ll → unsigned 'long long' limit
                            warnings.warn(f"L2DB helper num2bin(n): 'n' is too high to store in L2DB (max is {ll})")
                            return b''
                    else: # Must be represented as signed, thus lower boundary
                        if n in range(-127, 128): # Can be represented as char
                            return struct.pack('>b', n)
                        elif n in range(-32768, 32768): # Can be represented as short
                            return struct.pack('>h', n)
                        elif n in range(-2147483648, 2147483648): # Can be represented as int
                            return struct.pack('>i', n)
                        elif n in range(-9223372036854775808, 9223372036854775808): # Can be represented as long long
                            return struct.pack('>q', n)
                        else:
                            llmin, llmax =  -9223372036854775808, 9223372036854775807
                            warnings.warn(
                        f"L2DB helper num2bin(n): 'n' is too large to store in L2DB (must be {llmin} >= num >= {llmax})"
                            )
                case 'float':
                    if unsigned:
                        warnings.warn('L2DB helper num2bin(n): Floating point numbers cannot be unsigned')
                    # I had no better way of doing that other than trying and seeing if it's failing...
                    try:
                        return struct.pack('>f', n)
                    except struct.error:
                        try:
                            return struct.pack('>d', n)
                        except struct.error:
                            warnings.warn(f"L2DB helper num2bin(n): Failed to store 'n' as float or double")
                            return b''
                case _:
                    warnings.warn(f"L2DB helper num2bin(n): 'n' is of type '{_}', must be a number")
                    return b''

        def bin2num(b, astype='uin'):
            match astype:
                case 'uin':
                    return struct.unpack('>Q', b.rjust(8, b'\0')) # An unsigned integer can easily be padded on
                    # the left with `\0`s without changing its numerical value, so I can save me a lot of checking here.
                case 'int':
                    match len(b):
                        case 0:
                            warnings.warn("L2DB helper bin2num(b): 'b' is empty")
                            return NaN
                        case 1:
                            return struct.unpack('>b', b)
                        case 2:
                            return struct.unpack('>h', b)
                        case 4:
                            return struct.unpack('>i', b)
                        case 8:
                            return

        def new_header(spec_ver=-0.1, index_len=0, flags=0):
            spec_ver = spec_ver if spec_ver>=0 else float('.'.join(spec_version.split('.')[0:2])) # spec_version is the
                                                                                                 # global version string
            return struct.pack(
                f'>QfiB{"B"*47}', # one unsigned long long, one float, one int, one unsigned float, 47B of padding
                9821280156134670336, # File magic, gets packed to b'\x88L2DB\x00\x00\x00'
                spec_ver,
                index_len,
                flags,
                *(0 for _ in range(47))
            )

        def get_headerdata(header):
            headerdata = struct.unpack(f'>QfiB{"B"*47}', header)
            return {
                'magic': struct.pack('>Q', headerdata[0]), # Should be b'\x88L2DB\x00\x00\x00'
                'spec_ver': round(headerdata[1], 3), # Minor version cannot be above 999
                                      # but rounding is necessary because floats suck and cannot keep most numbers exact
                'idx_len': headerdata[2],
                'flags': headerdata[3]
            }

        help_funcs = locals()
        return {fn:help_funcs[fn] for fn in which}

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
