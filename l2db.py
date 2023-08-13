#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import _io # Only used for type hints

spec_version:str = '1.2.0' # See SPEC.md
implementation_version:str = '0.3.5-pre-alpha+python3-above-.7'

__doc__:str = f"""
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
NaN:float = float('NaN') # Somehow has no number literal, can only be gotten through a float of the string 'NaN'.
Infinity:float = float('Infinity') # Same here, but here two strings ('inf' and 'infinity') are both valid for float().

class L2DBError(Exception):
    """L2DB base exception"""
    def __init__(self, message:str='') -> None:
        self.message = message
        super().__init__(self.message)

class L2DBVersionMismatch(L2DBError):
    """Raised when conversion between spec versions fails"""
    # imp_ver stands for "implemented version" in this case, not "implementation version".
    def __init__(self, db_ver:str='0.0.0-please+replace', imp_ver:str=spec_version) -> None:
        self.message = f'database follows spec version {db_ver} but implementation follows spec version {imp_ver}. Conversion failed.'
        super().__init__(self.message)

class L2DBTypeError(L2DBError):
    """Raised when conversion between value types fails"""
    def __init__(self, key:str='', vtype:str='inv') -> None: # Renamed `type` to `vtype`: `type` is a Python3-builtin
        toreplace:tuple = ("'", "\\'")
        self.message = f"Could not convert key '{key.replace(*toreplace)}' to type '{vtype.replace(*toreplace)}'" if (
                key!=None) else f"Could not convert value to type '{vtype.replace(*toreplace)}'"
        super().__init__(self.message)

class L2DBKeyError(L2DBError):
    """Raised when an unaccessible key is accessed"""
    def __init__(self, key:str='') -> None:
        toreplace = ("'", "\\'")
        self.message = f"Key '{key.replace(*toreplace)}' could not be found"
        super().__init__(self.message)

########
# L2DB #
########

#TODO: implement this, store internally (if buffered) as b-string with the whole db inside
# to make it easier to implement file mode

class L2DB:
    __doc__:str = f'L2DB {spec_version} in implementation {implementation_version}'
    spec:str = spec_version
    implementation:str = implementation_version
    def __init__(
            self,
            source:dict[str, str|int|float|bytes|bool|None]|_io.BytesIO|_io.BufferedRandom|str,
            mode:str='rw',
            runtime_flags:tuple=()
    ) -> None:
        self.__db:dict[str, str|int|float|bytes|bool|None] = {}
        self.source:dict[str, str|int|float|bytes|bool|None]|_io.BytesIO|_io.BufferedRandom|str = source
        self.mode:str = mode
        self.runtime_flags:tuple = runtime_flags
        self.open(source, mode, runtime_flags)

    def __helpers(self, which:tuple=()) -> dict[str, any]:
        """Returns the helper functions for internal use.
        As an argument, supply either a tuple with the string names of the specific functions you need
        or an empty tuple to get all.
        If a non-existing function is requested a KeyError will be raised. """
        import struct

        def overwrite_in_file(path:str, offset:int, data:bytes) -> bytes:
            """Overwrite only `len(data)` bytes in file `path` beginning at `offset`"""
            with open(path, 'r+b') as f:
                f.seek(offset)  # Move the file pointer to the desired position
                f.write(data)  # Write the new data, overwriting the existing content at that position
            return data

        def getbit(seq:int, pos:int) -> int:
            """Get only the bit at offset `pos` from the right in number `seq`."""
            return 1 & (seq >> pos)

        def str2bin(s:str):
            """Converts a string to a UTF-8 encoded byte string.
            Exists more as a reminder to me that strings have the encode method."""
            return s.encode('utf-8')

        def bin2str(b:bytes):
            """Converts a UTF-8 encoded binary string to a string.
            Exists more as a reminder to me that b-strings have the decode method."""
            return b.decode('utf-8')

        def num2bin(n:int|float, unsigned:bool=False) -> bytes:
            """Converts a number object to binary for storage in L2DB"""
            if n==NaN:
                warnings.warn('L2DB helper num2bin(n): cannot store NaN')
                return b'\0'
            match type(n).__name__:
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
                            warnings.warn(f"L2DB helper num2bin(n): Failed to store {n} as float or double")
                            return b''
                case other:
                    warnings.warn(f"L2DB helper num2bin(n): 'n' is of type '{other}', must be a number")
                    return b''

        def bin2num(b:bytes, astype:str='uin') -> int|float:
            """Converts a binary string to a number for usage"""
            match astype:
                case 'uin':
                    return struct.unpack('>Q', b.rjust(8, b'\0'))[0] # An unsigned integer can easily be padded
                        # on the left with `\0`s without changing its numerical value,
                        # so I can save me a lot of checking here.
                case 'int':
                    match len(b):
                        case 1:
                            return struct.unpack('>b', b)[0]
                        case 2:
                            return struct.unpack('>h', b)[0]
                        case 4:
                            return struct.unpack('>i', b)[0]
                        case 8:
                            return struct.unpack('>q', b)[0]
                        case other:
                            warnings.warn(
                                f"L2DB helper bin2num(b): 'b' has invalid length of {other} (must be 1, 2, 4 or 8)"
                            )
                            return NaN
                case 'flt':
                    match len(b):
                        case 4:
                            return struct.unpack('>f', b)
                        case 8:
                            return struct.unpack('>d', b)
                        case other:
                            warnings.warn(f"L2DB helper bin2num(b): invalid buffer length for float (is {other}, must be 4 or 8)")
                            return NaN

        def flag2flag(flags:tuple[str]|int) -> int|tuple[str]|None:
            """Turns a flag tuple into flag int and the other way around.
            Silently discards any invalid flag names/bits."""
            if type(flags)==tuple:
                rflags:int = 0b00000000 # All flags unset
                if 'LOCKED' in flags:
                    rflags += 0b00000100
                if 'DIRTY' in flags:
                    rflags += 0b00000010
                if 'X64_INDEXES' in flags:
                    rflags += 0b00000001
                return rflags
            elif type(flags)==int:
                rflags:list[str] = [] # No flags set
                if getbit(seq=flags, pos=2): # getbit counts from the end, not the start
                    rflags.append('LOCKED')
                if getbit(seq=flags, pos=1):
                    rflags.append('DIRTY')
                if getbit(seq=flags, pos=0):
                    rflags.append('X64_INDEXES')
                return tuple(rflags)
            else:
                warnings.warn(f"L2DB helper flag2flag(flags): invalid flag format '{type(flags).__name__}' (must be 'tuple[str]' or 'int')")
                return None

        def new_header(spec_ver:float=-0.1, index_len:int=0, flags:int=0) -> bytes:
            """Generates a new header byte string based on the given data"""
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

        def get_headerdata(header:bytes) -> dict[str, bytes|int]:
            """Extracts the header data from a given byte string of length 64"""
            headerdata = struct.unpack(f'>QfiB{"B"*47}', header)
            if headerdata[0]!=9821280156134670336:
                warnings.warn('L2DB helper get_headerdata(header): invalid file magic')
            return {
                'magic': struct.pack('>Q', headerdata[0]), # Should be b'\x88L2DB\x00\x00\x00'
                'spec_ver': round(headerdata[1], 4), # Minor version cannot be above 9999
         # but rounding is necessary because floats suck and cannot keep most numbers exact (e.g. 1.1→1.100000023841858)
                'idx_len': headerdata[2],
                'flags': headerdata[3]
            }

        help_funcs:dict[str, any] = locals()
        return {fn:help_funcs[fn] for fn in (which or help_funcs) if not fn in ('struct', '__builtins__')}
                # Returns either the specified or all if 'which' tuple is falsey (empty)
                # Excludes all that are in the exclude list

    def open(
            self,
            source:dict[str, str|int|float|bytes|bool|None]|_io.BytesIO|_io.BufferedRandom|str,
            mode:str='rw',
            runtime_flags:tuple[str]=()
    ) -> any:
        """Populates the L2DB with new content and sets its source location if applicable.
        Accepts modes 'r', 'w', 'f' and any combination of those three."""

    def read(self, key:str, vtype:str|None=None) -> str|int|float|bytes|bool|None:
        """Returns the value of the key, optionally converts it to `vtype`.
        Raises an L2DBKeyError if the key is not found.
        Raises an L2DBTypeError if the value cannot be converted to the specified `vtype`."""

    def write(
            self,
            key:str,
            value:str|int|float|bytes|bool|None,
            vtype:str|None=None
    ) -> dict[str, str|int|float|bytes|bool|None]:
        """Writes `value` to `key`, optionally converts it to `vtype`.
        Raises an L2DBKeyError if the key name is invalid.
        Raises an L2DBTypeError if the value cannot be converted to the specified `vtype`."""

    def delete(self, key:str) -> dict[str, str|int|float|bytes|bool|None]:
        """Removes a key from the L2DB."""

    def convert(self, key:str, vtype:str|None, fromval:str|int|float|bytes|bool|None):
        """Converts the key or value to type `vtype`."""

    def dump(self) -> dict[str, str|int|float|bytes|bool|None]:
        """Dumps all key-value pairs as a `dict`"""

    def dumpbin(self) -> bytes:
        """Dumps the whole database as a binary string"""

    def flush(self, file:_io.BytesIO|_io.BufferedRandom|str|None=None, move:bool=False) -> None:
        """Flushes the buffered changes to the file the database has been initialized with.
        If a file is specified this flushes the changes to that file instead and changes the database source to the new
        file if `move` is True.
        Raises a FileNotFoundError with the message 'No file specified' if the database has no source file and none is
        specified."""

    def cleanup(self, only_flag:bool=False, dont_rescue:bool=False) -> dict[str, str]:
        """Tries to repair the database and unsets the `DIRTY` flag.
        Skips all repairs if `only_flag` is True.
        Discards corrupted key-value pairs instead of rescuing them if `dont_rescue` is True."""

########
# Test #
########

if __name__ == '__main__':
    try:
        db:L2DB = L2DB({'hello':'world','key':'value','some number':42,'Does bool exist?':True})
        print(db.dump())
        db2:L2DB = L2DB(db.source)

    except Exception as e:
        print('''Could unfortunately not demo the database functionality!
The following technical mumbo jumbo should show what went wrong:''')
        from traceback import format_exc as show_last_traceback

        print(show_last_traceback())
