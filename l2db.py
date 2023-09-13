#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from io import FileIO, BytesIO, BufferedReader, BufferedRandom, BufferedWriter # Used for type hinting
from types import TracebackType                                                # Used for type hinting
from traceback import format_exception

spec_version:str = '2.0.0' # See SPEC.md
implementation_version:str = '0.3.9-pre-alpha+python3-above-.7'

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
import struct, sys
NaN:float = float('NaN') # Somehow has no number literal, can only be gotten through a float of the string 'NaN'.
Infinity:float = float('Infinity') # Same here, but here two strings ('inf' and 'infinity') are both valid for float().

class L2DBError(Exception):
    """L2DB base exception"""
    def __init__(self, message:str='') -> None:
        self.message = message
        super().__init__(self.message)

class L2DBIsDirty(L2DBError):
    def __init__(self):
        self.message = 'Cannot write to dirty database'
        super().__init__(self.message)

class L2DBVersionMismatch(L2DBError):
    """Raised when conversion between spec versions fails"""
    # imp_ver stands for "implemented version" in this case, not "implementation version".
    def __init__(self, db_ver:str='0.0.0-please+replace', imp_ver:str=spec_version) -> None:
        self.message = f'Major version mismatch ({db_ver} vs {imp_ver}). Conversion failed.'
        super().__init__(self.message)

class L2DBTypeError(L2DBError):
    """Raised when conversion between value types fails"""
    def __init__(self, key:str='', vtype:str='inv') -> None: # Renamed `type` to `vtype`: `type` is a Python3-builtin
        toreplace:tuple[str] = ("'", "\\'")
        self.message = f"Could not convert key '{key.replace(*toreplace)}' to type '{vtype.replace(*toreplace)}'" if (
                                        key!=None) else f"Could not convert value to type '{vtype.replace(*toreplace)}'"
        super().__init__(self.message)

class L2DBKeyError(L2DBError):
    """Raised when an unaccessible key is accessed"""
    def __init__(self, key:str='') -> None:
        toreplace:tuple[str] = ("'", "\\'")
        self.message = f"Key '{key.replace(*toreplace)}' could not be found"
        super().__init__(self.message)

########
# L2DB #
########

class L2DB:
    __doc__:str = f'L2DB {spec_version} in implementation {implementation_version}'
    spec:str = spec_version
    implementation:str = implementation_version
    
    def __warn(self, *msg, **kwargs):
        """Print a message to stderr. Identical to `print` except no `file=` parameter"""
        return print(*msg, file=sys.stderr, **kwargs)
    
    def __init__(self,
            source:dict[str, str|int|float|bytes|bool|None]\
                   |BytesIO|FileIO|BufferedReader|BufferedRandom|BufferedWriter|str,
            mode:str='rw',
            runtime_flags:tuple=()
    ) -> None:
        self.__db:dict[str,bytes] = {'header': self.__helpers()['new_header'](), 'index': b'', 'values': b''}
        self.__source:dict[str,str|int|float|bytes|bool|None]\
                    |BytesIO|BufferedReader|BufferedRandom|BufferedWriter|str = source
        self.__fileref:BytesIO|FileIO|BufferedReader|BufferedRandom|BufferedWriter|None = None
        self.__mode:str = mode
        self.runtime_flags:tuple = runtime_flags
        self.open(source, mode, runtime_flags)

    source = property((lambda self: self.__source.copy() if type(self.__source)==dict else self.__source))
    mode = property((lambda self: self.__mode))

    def __enter__(self):
        """Enable L2DB to be used as a Context Manager."""
        return self

    def __exit__(self,
            err_type:BaseException|None=None,
            err_val:BaseException|None=None,
            err_tb:TracebackType|None=None) -> bool|None:
        """Enable L2DB to be used as a Context Manager.
        This method flushes, then clears the opened database
        and handles any error raised but not caught inside the context."""
        try:
            self.flush() # Save all changes to disk if necessary
        except Exception as err:
            print(f'''[!] Error while flushing L2DB after context manager:\n{"".join(
                       format_exception(type(err), err, err.__traceback__))}\n   --> Some data may have gotten lost.''')
        self.__source = None
        self.__mode = ''
        self.__db = {'header': b'', 'index': b'', 'values': b''}
        self.__del__() # Run the destructor manually to ensure it's run.
        if err_type: # If an error was passed to the context manager
            print(f'''\n\n[!] L2DB context manager cought an exception:\n{"".join(
                  format_exception(err_type, err_val, err_tb))}\n   --> Exception handled in L2DB context manager.\n''')
            return True # Signal that the error has been handled
        

    def __helpers(self, which:tuple=()) -> dict[str, any]:
        """Returns the helper functions for internal use.
        As an argument, supply either a tuple with the string names of the specific functions you need
        or an empty tuple to get all.
        If a non-existing function is requested a KeyError will be raised. """

        def get_type(val:bytes|str|float|int|bool|None):
            """Determine the L2DB type of any given value"""
            match type(val).__name__:
                case 'bytes':
                    return 'raw'
                case 'str':
                    return 'str'
                case 'float':
                    return 'flt' # Later change the default to 'fpn', ASAP
                case 'int':
                    if val<=struct.unpack('>q', b'\x7f\xff\xff\xff\xff\xff\xff\xff')[0]: # Representable as signed long
                        return 'int'
                    else: # Not representable as signed long
                        return 'uin'
                case 'bool':
                    return 'bol'
                case 'NoneType':
                    return 'nul'
                case other:
                    self.__warn(f'L2DB helper get_type(): No L2DB type for Python type {repr(other)}')
                    return 'inv'


        def overwrite_in_file(file:str|BufferedRandom|BufferedWriter|FileIO|BytesIO, offset:int, data:bytes) -> bytes:
            """Overwrite only `len(data)` bytes in file `path` beginning at `offset`"""
            if type(file)==str:
                with open(file, 'r+b') as f:
                    f.seek(offset)  # Move the file pointer to the desired position
                    return f.write(data)  # Write the new data, overwriting the existing content at that position
            else:
                file.seek(offset)
                return file.write(data)

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
                self.__warn('L2DB helper num2bin(n): cannot store NaN')
                return b'\0'
            match type(n).__name__:
                case 'int':
                    if unsigned: # Requested to be represented as unsigned
                        if n<0: # Must pe represented as signed
                            self.__warn(f"L2DB helper num2bin(n): unsigned numbers cannot be less than zero")
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
                            self.__warn(f"L2DB helper num2bin(n): 'n' is too high to store in L2DB (max is {ll})")
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
                            self.__warn(
                        f"L2DB helper num2bin(n): 'n' is too large to store in L2DB (must be {llmin} >= num >= {llmax})"
                            )
                case 'float':
                    if unsigned:
                        self.__warn('L2DB helper num2bin(n): Floating point numbers cannot be unsigned')
                    fltmax:tuple[float] = struct.unpack(
                        '>ff',
                        b'\x019Dp\x7f\x7f\xff\xff'
                        # Min and max single-precision float value (2.2250738585072014e-308, 1.7976931348623157e+308)
                    )
                    dblmax:tuple[float] = struct.unpack(
                        '>dd',
                        b'\x00\x10\x00\x00\x00\x00\x00\x00\x7f\xef\xff\xff\xff\xff\xff\xff'
                        # Min and max double-precision float value (3.402823507664669e-38, 3.4028234663852886e+38)
                    )
                    if (n>fltmax[0])and(fltmax[1]>n):
                        return struct.pack('>f', n)
                    elif (n>dblmax[0])and(dblmax[1]>n):
                        return struct.pack('>d', n)
                    else:
                        try:
                            return struct.pack('>d', n) # Just try it if it failed the tests but is possible
                        except (struct.error, OverflowError) as err:
                            self.__warn(f"L2DB helper num2bin(n): Failed to store {n} as float or double")
                            return b''
                case other:
                    self.__warn(f"L2DB helper num2bin(n): 'n' is of type '{other}', must be a number")
                    return b''

        def bin2num(b:bytes, astype:str='uin') -> int|float:
            """Converts a binary string to a number for usage"""
            match astype:
                case 'uin':
                    return struct.unpack('>Q', b.rjust(8, b'\0'))[0] # An unsigned integer can easily be padded on the
                        # left with `\0`s without changing its numerical value, so I can save me a lot of checking here.
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
                            self.__warn(
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
                            self.__warn(f"""L2DB helper bin2num(b): invalid buffer length for float (is {other
                                                                                                  }, must be 4 or 8)""")
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
                self.__warn(f"""L2DB helper flag2flag(flags): invalid flag format '{type(flags)
                                                                         .__name__}' (must be 'tuple[str]' or 'int')""")
                return None

        def new_header(spec_ver:str='x.x.x', index_len:int=0, flags:int=0) -> bytes:
            """Generates a new header byte string based on the given data"""
            try:
                spec_ver = tuple(int(v) for v in (spec_ver if spec_ver!='x.x.x' else spec_version).split('.')[:3])
            except Exception as err:
                self.__warn(f'''L2DB helper new_header(): spec_ver has to be three positive full numbers{' '
                                                                            }separated by dots, no more and no less!''')
                spec_ver = tuple(int(v) for v in spec_version.split('.'))
            return struct.pack(
                f'>QHHHiB{"B"*45}', # one unsigned long long, one float, one int, one unsigned float, 47B of padding
                9821280156134670336, # File magic, gets packed to b'\x88L2DB\x00\x00\x00'
                *spec_ver,
                index_len,
                flags,
                *(0 for _ in range(45))
            )

        def get_headerdata(header:bytes) -> dict[str, bytes|int]:
            """Extracts the header data from a given byte string of length 64"""
            headerdata = struct.unpack(f'>QHHHiB{"B"*45}', header)
            if headerdata[0]!=9821280156134670336:
                self.__warn('L2DB helper get_headerdata(header): invalid file magic')
            return {
                'magic': struct.pack('>Q', headerdata[0]), # Should be b'\x88L2DB\x00\x00\x00'
                'spec_ver': '{}.{}.{}'.format(*headerdata[1:4]),
                'idx_len': headerdata[4],
                'flags': flag2flag(headerdata[5])
            }

        def set_flag(flagname:str) -> bool:
            """Set/unset a specific flag.
            Returns True if something changed, otherwise False."""
            match flagname[0]:
                case '+':
                    if self.__flag(flagname[1:]): # Flag is already set.
                        return False
                    else:
                        self.__db['header'][18] += flag2flag((flagname[1:],)) # Set the flag.
                        return True
                case '-':
                    if not self.__flag(flagname[1:]): # Flag is already unset.
                        return False
                    else:
                        self.__db['header'][18] -= flag2flag((flagname[1:],)) # Unset the flag.
                        return True
                case other:
                    self.__warn(f'L2DB helper set_flag(): invalid operand {repr(other)}! (must be plus or minus)')
                    return False

        def get_keyoffset(keyname:str, all:bool=False) -> tuple[int]|dict[str,tuple[int]]:
            """Finds a key's index offsets by name or dumps all index entries as a nested dict"""
            helpers = self.__helpers()
            validx_size:int = 16 if self.__flag('X64_INDEXES') else 8
            found_keys:dict[str,tuple[int]] = {}
            if 'f' in self.__mode:
                self.__fileref.seek(0)
                self.__db['header'] = self.__fileref.read(64)
                # Buffer the index:
                self.__db['index'] = self.__fileref.read(helpers['get_headerdata'](self.__db['header'])['idx_len'])
            buf:bytes = b''
            for byte in self.__db['index']:
                buf += bytes([byte])
                #print(f'{buf=}') #debug
                if len(buf)>validx_size+3 and byte==0: # Index entry end, buf should now be exactly one index entry
                    found_keys[buf[validx_size+3:-1].decode('utf-8')] = \
                                                struct.unpack(f'>{"II" if validx_size==8 else "QQ"}', buf[:validx_size])
                    buf = b'' # Reset buffer
                    if keyname in found_keys and not all:
                        return found_keys[keyname]
                    #TODO: Add type to little sub-dict and rewrite L2DB.read() and L2DB.write() for compatibility
            if all:
                return found_keys
            else:
                return (-1,-1)

        def _get_keyoffset(keyname:str) -> tuple[int]:
            """Retrieve an entries' start and end offset in the index.
            Thanks to ChatGPT-3.5 for the ideas that went into this finally working function!"""
            entry_size:int = 16 if self.__flag('X64_INDEXES') else 8
            name_to_find_bytes:bytes = keyname.encode('utf-8') + b'\x00'
            offset:int = 0
            while offset < len(self.__db['index']):
                entry_name_offset:int = self.__db['index'].find(name_to_find_bytes, offset)
                if entry_name_offset == -1:
                    break
                # Check if it's a valid entry by verifying the type prefix
                entry_type_offset:int = entry_name_offset - 3
                if entry_name_offset >= (entry_size + 3):
                    entry_type:str = self.__db['index'][entry_type_offset:entry_type_offset + 3].decode('utf-8')
                    if entry_type in ('raw', 'bol', 'int', 'uin', 'flt', 'fpn', 'str', 'nul', 'inv'):
                        start_offset:int = entry_name_offset-entry_size-3
                        end_offset:int = entry_name_offset+len(keyname)+1
                        return start_offset, end_offset
                offset = entry_name_offset + 1
            return -1,-1

            def checkver(imp:tuple[int],db:tuple[int]) -> tuple[bool|str]:
                """Check the implementation vs. database version"""



        help_funcs:dict[str, any] = locals()
        return {fn:help_funcs[fn] for fn in (which or help_funcs) if not fn in ('struct', '__builtins__')}
                # Returns either the specified or all if 'which' tuple is falsey (empty)
                # Excludes all that are in the exclude list

    def __flag(self, name:str):
        """Tell if a flag is set"""
        return name in self.__helpers()['flag2flag'](self.__db['header'][18])

    def open(self,
            source:dict[str, str|int|float|bytes|bool|None]\
                   |BytesIO|FileIO|BufferedReader|BufferedRandom|BufferedWriter|str,
            mode:str='rw',
            runtime_flags:tuple[str]=()
    ) -> any:
        """Populates the L2DB with new content and sets its source location if applicable.
        Accepts modes 'r', 'w', 'f' and any combination of those three.
        Note that 'w' isn't a pure write-only mode!"""
        helpers:dict[str,any] = self.__helpers()
        if type(source).__name__ in ('bytes', 'dict', 'str', 'BufferedReader', 'BufferedRandom', 'BufferedWriter'):
            if helpers['get_headerdata'](self.__db['header'])['idx_len']:
                self.__warn('Old content of L2DB has been discarded in favor of new content')
            self.__db:dict[str,bytes] = {'header': b'', 'index': b'', 'values': b''}
            self.__source:dict[str, str|int|float|bytes|bool|None]\
                        |BytesIO|BufferedReader|BufferedRandom|BufferedWriter|str = source
            self.__mode: str = mode
            self.runtime_flags: tuple = runtime_flags
            match type(self.__source).__name__:
                case 'bytes':
                    if 'f' in self.__mode.lower():
                        self.__warn('L2DB.open(): ')
                    self.__mode = f'''{"r" if "r" in self.__mode.lower() else ""}{"w"
                                                                               if "w" in self.__mode.lower() else ""}'''
                    idxlen:int = helpers['get_headerdata'](self.__source[:64])['idx_len']
                    self.__db = {
                        'header': self.__source[:64], # The header is always exactly 64 bytes long
                        'index': self.__source[64:64+idxlen],
                        'values': self.__source[64+idxlen:] # Everything after the index is values
                    }
                case 'dict':
                    self.__mode = f'''{"r" if "r" in self.__mode.lower() else ""}{"w"
                                                                               if "w" in self.__mode.lower() else ""}'''
                    self.__db = {
                        'header': helpers['new_header'](),
                        'index': b'',
                        'values': b''
                    }
                    for key in self.__source:
                        self.write(key=key, value=self.__source[key]) # Add all key-value pairs to DB
                case 'str'|'BufferedReader'|'BufferedRandom':
                    self.__mode = f'''{"r" if "r" in self.__mode.lower() else ""}{"w"
                                    if "w" in self.__mode.lower() else ""}{"f" if "f" in self.__mode.lower() else ""}'''
                    self.__fileref = (open(self.__source, f'r{"+" if "w" in self.__mode else ""}b')
                                      if type(self.__source)==str else self.__source)
                    self.__fileref.seek(0)
                    self.__db['header'] = self.__fileref.read(64)
                    if not 'f' in self.__mode:
                        headerdata = helpers['get_headerdata'](self.__db['header'])
                        self.__db['index'] = self.__fileref.read(headerdata['idx_len'])
                        self.__db['values'] = self.__fileref.read() # read the rest
                        self.__fileref.close()
                        self.__fileref = None
                    #TODO: Implement this!
                    # Note that only this sort of input supports unbuffered ('f', file) mode!
                case 'BufferedWriter':
                    self.__mode = f'''{"r" if "r" in self.__mode.lower() else ""}{"w"
                                                                               if "w" in self.__mode.lower() else ""}'''
                    self.__warn(
                        'L2DB.open(): given file reference is write-only, all previous content in that file is lost!'
                    )
                    self.__db = {
                        'header': helpers['new_header'](),
                        'index': b'',
                        'values': b''
                    }
        else:
            raise TypeError(f"""L2DB.open(): 'source' argument is of type '{type(source)
                                                    .__name__}' (must be 'bytes', 'dict', 'str' or 'BufferedReader')""")

    def read(self, key:str, vtype:str|None=None) -> str|int|float|bytes|bool|None:
        """Returns the value of the key, optionally converts it to `vtype`.
        Raises an L2DBKeyError if the key is not found.
        Raises an L2DBTypeError if the value cannot be converted to the specified `vtype`."""
        if self.__flag('DIRTY'):
            self.__warn('L2DB.read(): Database is dirty, you may get garbage data before next cleanup!')
        if not 'r' in self.__mode:
            raise L2DBError('L2DB.read(): database is write-only')
        helpers:list[any] = self.__helpers()
        if not 'f' in self.__mode:
            index_data = self.__db['index']
        else:
            self.__fileref.seek(0)
            self.__db['header'] = self.__fileref.read(64)
            #self.__fileref.seek(64) # Should automatically happen with the read action
            self.__db['index'] = self.__fileref.read(helpers['get_headerdata'](self.__db['header'])['idx_len'])
        keyoffsets = helpers['get_keyoffset'](key)
        if any(i<0 for i in keyoffsets):
            raise L2DBKeyError(key)
        #print(f'{keyoffsets=}') #debug
        entry = self.__db['index'][keyoffsets[0]:keyoffsets[1]]
        stored_type = self.__db['index'][keyoffsets[1]-(len(key)+1)-3:keyoffsets[1]-(len(key)+1)].decode('utf-8')
        #print(f'{stored_type=}\n{entry=}') #debug
        # Fetch raw value
        if self.__flag('X64_INDEXES'):
            voffsets = struct.unpack('>QQ', entry[:16])
        else:
            voffsets = struct.unpack('>II', entry[:8])
        #print(f'{voffsets=}') #debug
        rawvalue:bytes = b''
        if not 'f' in self.__mode:
            rawvalue = self.__db['values'][voffsets[0]:voffsets[1]]
        else:
            self.__fileref.seek(64+len(self.__db['index'])+voffsets[0]) # header + index + previous values
            rawvalue = self.__fileref.read(voffsets[1]-voffsets[0]) # Value length
        # Convert to usable type
        match stored_type:
            case 'raw':
                value = rawvalue
            case 'str':
                value = rawvalue.decode('utf-8')
            case 'int'|'uin'|'flt'|'fpn':
                value = helpers['bin2num'](rawvalue, stored_type)
            case 'bol':
                if rawvalue[0]==0:
                    return False
                elif rawvalue[0]==1:
                    return True
                else:
                    self.__warn(f'L2DB.read(): Invalidly stored boolean in key {key}!')
                    helpers['set_flag']('+DIRTY') # Set the DIRTY flag because this is a strict implementation
                    return True # It's a truey value, so I'll return True anyways.
            case 'nul':
                if rawvalue[0]==0:
                    return None
                else:
                    self.__warn(f'L2DB.read(): Invalidly stored null in key {key}!')
                    helpers['set_flag']('+DIRTY') # Set the DIRTY flag because this is a strict implementation
                    return None # It's of type 'nul', so I'll return None anyways.
            case other:
                self.__warn(f'L2DB.read(): Unknown format {repr(other)}, interpreting as \'raw!\'')
                helpers['set_flag']('+DIRTY') # Set the DIRTY flag
                value = rawvalue
        # If user wants to read as another type, convert it
        if vtype:
            return self.convert(None, vtype, value)
        else:
            return value
        toreplace = ("'", r"\'") # Cannot use backslashes in format strings' inserts, so I do this workaround.
        raise L2DBKeyError(f"'{key.replace(*toreplace)}' could not be found")

    def write(
            self,
            key:str,
            value:str|int|float|bytes|bool|None,
            vtype:str|None=None
    ) -> dict[str, str|int|float|bytes|bool|None]:
        """Writes `value` to `key`, optionally converts it to `vtype`.
        Raises an L2DBKeyError if the key name is invalid.
        Raises an L2DBTypeError if the value cannot be converted to the specified `vtype`."""
        if self.__flag('DIRTY'):
            raise L2DBIsDirty() # Refuse to write to dirty database
        if not 'w' in self.__mode:
            raise L2DBError('L2DB.write(): database is read-only')
        helpers = self.__helpers()
        # Fetch index entry
        keyoffsets = helpers['get_keyoffset'](key)
        if any(i<0 for i in keyoffsets):
            keyoffsets = (
                len(self.__db['index']),
                (len(self.__db['index'])+(16+3 if self.__flag('X64_INDEXES') else 8+3)+len(key)+1)
            )
            entry:bytes = b''.join((
                struct.pack(f'>{"QQ" if self.__flag("X64_INDEXES") else "II"}', *keyoffsets),
                (vtype or helpers['get_type'](value)).encode('utf-8'),
                key.encode('utf-8'),
                b'\0'
            ))
        else:
            entry:bytes = self.__db['index'][keyoffsets[0]:keyoffsets[1]]
        stored_type:str = self.__db['index'][keyoffsets[1]-(len(key)+1)-3:keyoffsets[1]-(len(key)+1)].decode('utf-8')
        # print(f'{stored_type=}\n{entry=}') #debug
        orig_idx_len:int = len(self.__db['index'])
        # Fetch raw value
        if self.__flag('X64_INDEXES'):
            voffsets = struct.unpack('>QQ', entry[:16])
        else:
            voffsets = struct.unpack('>II', entry[:8])
        # Decide whether to write to the current data space or to move the key to the end of the DB.
        newtype = vtype or stored_type
        if newtype!=stored_type and newtype in ('int', 'uin', 'flt', 'fpn', 'bol', 'str', 'raw', 'nul'):
            stored_type = self.__db['index'][keyoffsets[1]-(len(key)+1)-3:keyoffsets[1]-(len(key)+1)]\
                                                                                               = newtype.encode('utf-8')
        valbin:bytes = b''
        match type(value).__name__:
            case 'bytes':
                valbin = value
            case 'str':
                valbin = helpers['str2bin'](value)
            case 'int'|'float':
                valbin = helpers['num2bin'](value)
            case other:
                self.__warn(f'''L2DB.write(): Could not assign value of type {repr(other)
                                                                                } to key of type {repr(stored_type)}''')

        #TODO: Find out why it misbehaves!
        # Add headerdata modification!
        # Note that some of the indexes in the if block below seem to be off, also don't forget to merge the type prefix
        #  in with the rest!
        if len(valbin)<=voffsets[1]-voffsets[0]:
            if not 'f' in self.__mode:
                try:
                    prev_val:bytes = self.__db['values'][:voffsets[0]]
                except IndexError:
                    prev_val:bytes = b''
                try:
                    aftr_val = self.__db['values'][voffsets[0]+len(valbin):]
                except IndexError:
                    aftr_val:bytes = b''
                print(f'{prev_val=}\n{aftr_val=}\n{valbin=}')
                self.__db['values'] = b''.join((prev_val,valbin,aftr_val))
                if len(valbin)<voffsets[1]-voffsets[0]: # Update the index to represent the new value length:
                    try:
                        prev_idx:bytes = self.__db['index'][:(64+keyoffsets[0]+8)]
                    except IndexError:
                        prev_idx:bytes = b''
                    try:
                        aftr_idx:bytes = self.__db['index'][
                                               (64+keyoffsets[0]+(8 if self.__flag('X64_INDEXES') else 4)+len(valbin)):]
                    except IndexError:
                        aftr_idx:bytes = b''
                    self.__db['index'] = b''.join((
                        prev_idx,
                        (struct.pack('>Q', voffsets[1]) if self.__flag('X64_INDEXES')
                            else struct.pack('>I', voffsets[1])),
                        aftr_idx
                    ))
            else:
                self.__helpers()['overwrite_in_file'](self.__fileref, voffsets[0], valbin)
                if len(valbin)<voffsets[1]-voffsets[0]: # Update the index to represent the new value length:
                    if self.__flag('X64_INDEXES'):
                        helpers['overwrite_in_file'](
                            self.__fileref,
                            (64+keyoffsets[0]+8),
                            struct.pack(
                                '>Q',
                                (voffsets[1]-((voffsets[1]-voffsets[0])-len(valbin)))
                            )
                        )
                    else:
                        helpers['overwrite_in_file'](
                            self.__fileref,
                            (64+keyoffsets[0]+4),
                            struct.pack(
                                '>I',
                                (voffsets[1]-((voffsets[1]-voffsets[0])-len(valbin)))
                            )
                        )


    def delete(self, key:str) -> dict[str, str|int|float|bytes|bool|None]:
        """Removes a key from the L2DB."""
        ... #TODO: Implement deletion mechanism here!

    def convert(self, key:str, vtype:str|None, fromval:str|int|float|bytes|bool|None):
        """Converts the key or value to type `vtype`."""
        ... #TODO: Implement converter here!

    def dump(self) -> dict[str, str|int|float|bytes|bool|None]:
        """Dumps all key-value pairs as a `dict`"""
        ... #TODO: Implement dumping mechanism here!
            # E.g. just evaluate the whole index "the old way" (the same way as L2DBv3 did)

    def dumpbin(self) -> bytes:
        """Dumps the whole database as a binary string"""
        if not 'f' in self.__mode:
            return b''.join((self.__db['header'],self.__db['index'],self.__db['values']))
        else:
            self.__fileref.seek(0)
            return self.__fileref.read() # Return the whole DB file's contents

    def flush(self, file:FileIO|BytesIO|BufferedRandom|BufferedWriter|str|None=None, move:bool=False) -> None:
        """Flushes the buffered changes to the file the database has been initialized with.
        If a file is specified this flushes the changes to that file instead and changes the database source to the new
        file if `move` is True.
        Raises a FileNotFoundError with the message 'No file specified' if the database has no source file and none is
        specified."""
        match type(file).__name__:
            case 'FileIO'|'BytesIO'|'BufferedRandom'|'BufferedWriter':
                if move or (not 'f' in self.__mode):
                    file.seek(0)
                    file.write(self.__dumpbin())
                if move:
                    if self.__fileref:
                        self.__fileref.close()
                    self.__source = file
                    self.__fileref = file if 'f' in self.__mode else None
            case 'str':
                if move or (not 'f' in self.__mode):
                    file.seek(0)
                    file.write(self.__dumpbin())
                if move:
                    if self.__fileref:
                        self.__fileref.close()
                    self.__source = file
                    self.__fileref = open(self.__source, 'r+b') if 'f' in self.__mode else None
            case 'NoneType':
                if self.__fileref:
                    self.__fileref.seek(0)
                    self.__fileref.write(self.dumpbin())
            case other:
                self.__warn(f'''L2DB.flush(): Cannot flush to target file: reference is of wrong type {
                                                                                         repr(type(other).__name__)}''')

        # Ensure all contents are actually written to the file on disk.
        if self.__fileref:
            self.__fileref.flush()

    def __del__(self):
        """Properly disposes of this L2DB instance"""
        self.__delete__(self)

    def __delete__(self, instance):
        """Properly disposes of a deleted L2DB"""
        instance.flush()
        if instance.__fileref:
            instance.__fileref.close()
        if 'VERBOSE' in instance.runtime_flags:
            match type(instance.source).__name__:
                case 'str':
                    print(f'Disposed of L2DB({repr(instance.source)}, {repr(instance.mode)})')
                case 'bytes':
                    print(f'Disposed of L2DB(bytes, {repr(instance.mode)})')
                case 'FileIO'|'BufferedReader'|'BufferedRandom'|'BufferedWriter':
                    print(f'Disposed of L2DB({repr(instance.source.name)}, {repr(instance.mode)})')
                case 'BytesIO':
                    print(f'Disposed of L2DB(BytesIO, {repr(instance.mode)})')
                case 'dict':
                    print(f'Disposed of L2DB(dict, {repr(instance.mode)})')
                case other:
                    print(f'Disposed of L2DB({other}, {repr(instance.mode)})')

    def cleanup(self, only_flag:bool=False, dont_rescue:bool=False) -> dict[str, str]:
        """Tries to repair the database and unsets the `DIRTY` flag.
        Skips all repairs if `only_flag` is True.
        Discards corrupted key-value pairs instead of rescuing them if `dont_rescue` is True."""
        helpers = self.__helpers()
        ... #TODO: Implement the cleamup mechanism here!
        helpers['set_flag']('-DIRTY') # Unset the DIRTY flag.

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
