#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
L2DB ver.2
→ directory structure emulated with dots in the names and stored in 1st format to make it harder to manually decompile manually
The first 64 bytes are metadata as in L2DBver.1,
    the first 8 of which are the "file magic".
    The file magic is followed by the implementation version
    that is followed by a 4-byte-long UNSIGNED_INT32 for the DIRTREE length
    that is followed by another UNSIGNED_INT32 for the IDTAB length
    which is followed by other potential metadata.
The metadata are followed by a JSON-formatted DIRTREE, containing the variable names and as values their IDs.
    The same ID can be used several times to store duplicate values only once.
The DIRTREE is followed by the IDTAB (ID table) that is formatted as follows:
    4 bytes ID, 8 bytes starting index, [...], 4 bytes unused ID, 8 bytes VALTAB's length
The IDTAB is followed by the DATA block, just all values concatenated directly after one another,
    can only be separated by using the IDTAB block. The names begin with an ASCII representation of their type
    `type(obj).__name__` (separated using one underscore, the name itself can still contain underscores that don't get
    split away). The values are stored either as the raw data (if supported) or an ASCII representation of them
    `repr(obj)`.
"""

#TODO: Implement all unsupported types by setting the type part of the value to type(obj).__name__ and the value part of the value to repr(obj)!

import json

class L2DBError(BaseException):
    """General error in the l2db module."""
    ...


class L2DBSyntaxError(SyntaxError):
    """Syntax error in a L2DB file or byte-string."""
    ...


class L2DB:
    """L2DB - The __database class that implements reading and writing of L2DB files."""
    #TODO: Make internal functions and variables harder to access from outside!
    def __init__(self, source={}, ign_corrupted_source=False):
        """Initializes the L2DB object."""
        self.__registered_types = {}
        self.__source_file = source if type(source) == str else '<bytes object>' if type(source) == bytes \
            else '<dict object>'
        self.__strict = True
        self.strict = not ign_corrupted_source
        self.db = None
        # Default metadata, only kept when L2DB created from dict:
        self.metadata = {'VER': self.implementation_version, 'VALTABLE_LEN': 0, 'DB_INDEX_TYPE': 2, 'RAW_VALUES': False}
        self.valtable = {}
        self.database = {}
        if type(source) == bytes:
            self.eval_db(source)
        elif type(source) == str:
            self.load_db(source)
        elif type(source) == dict:
            self.db = source
        else:
            raise TypeError(f"unsupported source type for l2db: '{type(source).__name__}' (expected 'str' or 'bytes')!")

    def __set_strictness(self, strictness):
        """Per standard the strictness is True (complain about every error, even non-critical ones),
but can be set to False (complain only about critical errors) using this method."""
        self.__strict = not not strictness

    strict = property((lambda self: bool(self.__strict)), __set_strictness)

    # Indicates the version of the implementation:
    implementation_version = property(lambda self: 2)
    # Indicates what index types are supported by this implementation of L2DB:
    supported_index_types = property(lambda self: (1, 2)) #TODO: remove this!

    def register_type(self, objtype, ftobin, ffrombin=None):
        """
        type:     str type name, what you get when you run type(your_object).__name__
        ftobin:   function that can convert the object to binary, must take exactly one argument (obj) and return
                  a binary string.
        ffrombin: (optional) function that takes exactly one object (bstr) and returns any object

        Example setup:
        >>> class TestObject:
        ...     ...
        ...
        >>> def tobj_tobin(obj):
        ...     return b'\x00'
        ...
        >>> def tobj_frombin(bstr):
        ...     return TestObject()
        ...
        >>> __database.register_type('TestObject', tobj_tobin, tobj_frombin)
        {'objtype': 'TestObject', 'ftobin': <function tobj_tobin at 0x000000000000>,
            'ffrombin': <function tobj_frombin at 0x000000000000>}
        """
        self.__registered_types.update({str(type): [ftobin, ffrombin]})
        return {'objtype': objtype, 'ftobin': ftobin, 'ffrombin': ffrombin}

    def __helpers(self, which=None):
        """Return helper functions, select a subset or a single one of those using the which argument.
        These functions are little helpers. Some of them use the struct module,
        the formatting characters are described here:  https://docs.python.org/3.7/library/struct.html#format-characters
        and the '>' is described here:     https://docs.python.org/3.7/library/struct.html#byte-order-size-and-alignment
        """
        def str_from_bstr(bstr):
            return ''.join([chr(l) for l in bstr])
        def bstr_from_str(strng):
            return bytes([ord(l) for l in strng])
        def ins_into_bstr(bstr,idx,val):
            bstr_list = list(bstr)
            bstr_list[idx]=(val if type(val)==int else val[0] if type(val)==bytes else int(val)) # Ensure that the new
            # value is an integer so it can be interpreted as a byte.
            return bytes(bstr_list)
        def long_from_bstr(bstr, unsigned=False):
            import struct
            return struct.unpack(f'>{"Q" if unsigned else "q"}', bstr[0:8])[0]
        def int_from_bstr(bstr, unsigned=False):
            import struct
            return struct.unpack(f'>{"I" if unsigned else "i"}', bstr[0:4])[0]
        def float_from_bstr(bstr):
            import struct
            return struct.unpack('>f', bstr[0:4])[0]
        def double_from_bstr(bstr):
            import struct
            return struct.unpack('>d', bstr[0:8])[0]
        def bstr_from_long(num,unsigned=False):
            import struct
            return struct.pack(f'>{"Q" if unsigned else "q"}', num)
        def bstr_from_int(num,unsigned=False):
            import struct
            return struct.pack(f'>{"I" if unsigned else "i"}', num)
        def bstr_from_float(fnum):
            import struct
            return struct.pack('>f', fnum)
        def bstr_from_double(dnum):
            import struct
            return struct.pack('>d', dnum)
        def ret_as_dict(obj):
            return obj.__db if type(obj) == L2DB else obj if type(obj) == dict else dict(obj)

        helper_functions = locals() # puts all local variables into a dict
        helper_functions.pop('__doc__', None) # Remove  key '__doc__' from dict's contents if needed.
                                              # The second argument specifies the return value if the key is not found.

        # Decide what functions to give back:
        if which == None:
            return helper_functions
        elif type(which) == str:
            return helper_functions[which]
        elif type(which) in [tuple, list, set, frozenset]:
            return {name: helper_functions[name] for name in which}
        else:
            raise TypeError(f"unsupported selector for L2DB.helpers: '{type(which).__name__}'\
            (expected 'NoneType', 'str', 'tuple', list', 'set' or 'frozenset')")

    def __set_db(self, db):
        """Changes the __database dict of the L2DB object directly but enforces a type of 'dict'."""
        self.db = dict(db)

    database = property((lambda self: self.__db), __set_db)
    magic = property(lambda self: b'\x88L2DB\x00\x00\x00')

    def load_db(self, file):
        """Reads the __database file whose name is provided and stores and
returns a dictionary containing all the name-value pairs from the __database. """
        with open(file, 'rb') as dbf:  # dbf: DataBase-File
            return self.eval_db(dbf.read())

    def write_db(self, file):
        """Writes the __database to the file with the given path. Returns the binary representation of the file."""
        db = self.create_db()
        with open(file, 'wb') as dbf:  # dbf: DataBase-File
            dbf.write(db) # Put into a variable beforehand to run as little code as possible within file context manager
        return db

    def eval_db(self, database):
        """Reads the __database from the provided bytestring."""
        # Metadata
        metadata = database[0:64]
        if self.strict and metadata[0:8] not in (b'\x88L2DB\x00\x00\x00', b'\x88L2020DB'):
            raise L2DBSyntaxError(f"The magic bytes are incorrect: {metadata[0:8]} \
(expected b'\\x88L2DB\\x00\\x00\\x00' or b'\\x88L2020DB')")
        if self.strict and metadata[8] != self.implementation_version:
            raise L2DBError(f'Incompatible file version! ({metadata[8]}!={self.implementation_version})')
        self.update_metadata('DIRTREE_LEN', self.__helpers(which='int_from_bstr')(metadata[9:13], unsigned=True))
        self.update_metadata('IDTAB_LEN',   self.__helpers(which='int_from_bstr')(metadata[13:17], unsigned=True))

        # Dirtree
        dirtree = database[64:64 + self.metadata['DIRTREE_LEN']]
# TODO: recreate the commented-out code for the new version
#
#         buffer = []  # Create a buffer for the below for loop to store its bytes in
#         self.valtable.clear()  # Remove all contents from the current valtable
#         if self.metadata['DB_INDEX_TYPE'] == 2:
#             prev_valtable_entry = ''
#         cur_idx = (0, None)
#         for byte in valtable:
#             buffer.append(byte)
#             if len(buffer) == 8:
#                 match self.metadata['DB_INDEX_TYPE']:
#                     case 1:
#                         int_from_bstr = self.__helpers(which='int_from_bstr')
#                         cur_idx = (int_from_bstr(bytes(buffer[:4]), unsigned=True), int_from_bstr(bytes(buffer[4:]),
#                                                                                               unsigned=True))
#                     case 2:
#                         ...  # whole current buffer and next index is index tuple
#                         # (buffer, None), then in next iteration change index[1] to the next starting index.
#                         cur_idx = (self.__helpers(which='long_from_bstr')(bytes(buffer), unsigned=True), None)
#                     case _:
#                         if self.strict:
#                             raise L2DBError(f"DB_INDEX_TYPE of {self.metadata['DB_INDEX_TYPE']} is not supported, \
# expected one of {self.supported_index_types}!")
#
#             elif len(buffer) == (8 + 33) or buffer[-1] == 0:
#                 if len(buffer) > 8:  # Avoid taking an index number with null-bytes in it as the end of the key's name!
#                     key = ''.join([chr(l) for l in buffer[8:-1]])
#                     self.valtable[key] = cur_idx
#                     if self.metadata['DB_INDEX_TYPE'] == 2:
#                         try:
#                             self.valtable[prev_valtable_entry] = (self.valtable[prev_valtable_entry][0], cur_idx[0])
#                         except KeyError as e:
#                             if not str(e) == "''":
#                                 raise
#                         prev_valtable_entry = key
#                     buffer = []
#
#         # Body
#         body = __database[64 + self.metadata['VALTABLE_LEN']:]
#
#         # - INSERT: correct last index in index if type 2 - #
#         if self.metadata['DB_INDEX_TYPE'] == 2:
#             for key in self.valtable:
#                 if self.valtable[key][1] == None:
#                     self.valtable[key] = (self.valtable[key][0], len(body))
#         # - INSERT END: correct last index in index if type 2 - #
#
#         match self.metadata['DB_INDEX_TYPE']:
#             case dbindextype if dbindextype in (1, 2):
#                 self.__db = {
#                     keyname: body[self.valtable[keyname][0]:self.valtable[keyname][1]]
#                     for keyname in self.valtable}
#
#             case _:
#                 if self.strict:
#                     raise L2DBError(f"DB_INDEX_TYPE of {self.metadata['DB_INDEX_TYPE']} is not supported, \
# expected one of {self.supported_index_types}!")
#         if not self.metadata['RAW_VALUES']:
#             helpers = self.__helpers()
#             for key in self.__db:
#                 try:
#                     match self.__db[key].split(b'\x00', 1)[0]:
#                         case req_type if req_type in (b'int', b'int32'):
#                             self.__db[key] = helpers['int_from_bstr'](self.__db[key].split(b'\x00', 1)[1])
#                         case req_type if req_type in (b'long', b'int64'):
#                             self.__db[key] = helpers['bstr_to_long'](self.__db[key].split(b'\x00', 1)[1])
#                         case req_type if req_type in (b'uint', b'uint32'):
#                             self.__db[key] = helpers['int_from_bstr'](self.__db[key].split(b'\x00', 1)[1], unsigned=True)
#                         case req_type if req_type in (b'ulong', b'uint64'):
#                             self.__db[key] = helpers['bstr_to_long'](self.__db[key].split(b'\x00', 1)[1], unsigned=True)
#                         case b'float':
#                             self.__db[key] = helpers['bstr_to_float'](self.__db[key].split(b'\x00', 1)[1])
#                         case b'double':
#                             self.__db[key] = helpers['bstr_to_double'](self.__db[key].split(b'\x00', 1)[1])
#                         case b'str':
#                             self.__db[key] = ''.join([chr(b) for b in self.__db[key].split(b'\x00', 1)[1]])
#                         case b'bool':
#                             self.__db[key] = not not self.__db[key].split(b'\x00', 1)[1][
#                                 0]  # Invert 2 times to get a boolean from the byte's integer value
#                         case req_type if req_type in (b'', b'bstr', b'bytes'):
#                             self.__db[key] = self.__db[key].split(b'\x00', 1)[
#                                 1]  # Just cut away the leading null-byte to not destroy the actual value
#                 except Exception as e:
#                     print(f"Couldn't assign type to entry '{key}' because of a {type(e).__name__}: {e}")

    def create_db(self):
        """Creates a __database file in a binary string and returns it."""
        valtable = b''
        body = b''
        helpers = self.__helpers()

        def to_bytes(obj):
            "Wrapper to many of the above-defined helper functions"
            match type(obj)():
                case '':  # str
                    return helpers['bstr_from_str'](obj) if self.metadata['RAW_VALUES'] \
                        else b'str\x00' + helpers['bstr_from_str'](obj)
                case bool(): # bool
                    return (b'\x01' if obj else b'\x00') if self.metadata['RAW_VALUES'] else (b'bool\x00\x01' if obj else b'bool\x00\x00')
                case 0:  # int
                    try:
                        return helpers['bstr_from_int'](obj) if self.metadata['RAW_VALUES'] \
                            else b'int\x00' + helpers['bstr_from_int'](obj)
                    except Exception as e1:
                        print(
                            f'Error while trying to convert {obj} to binary as signed integer:\n{type(e1).__name__}: {e1}')
                        try:
                            return helpers['bstr_from_long'](obj) if self.metadata['RAW_VALUES'] \
                                else b'long\x00' + helpers['bstr_from_long'](obj)
                        except Exception as e2:
                            print(
                                f'Error while trying to convert {obj} to binary as signed long long:\n{type(e2).__name__}: {e2}')
                            return helpers['bstr_from_long'](obj, unsigned=True) if self.metadata['RAW_VALUES'] \
                                else b'ulong\x00' + helpers['bstr_from_long'](obj, unsigned=True)
                case 0.0:  # float
                    try:
                        return helpers['bstr_from_float'](obj) if self.metadata['RAW_VALUES'] \
                            else b'float\x00' + helpers['bstr_from_float'](obj)
                    except OverflowError:
                        return helpers['bstr_from_double'](obj) if self.metadata['RAW_VALUES'] \
                            else b'double\x00' + helpers['bstr_from_double'](obj)
                case b'':  # bytes
                    return obj if self.metadata['RAW_VALUES'] else b'\x00' + obj
                case _:  # If the type isn't one of the directly supported above...
                    return helpers['bstr_from_str'](repr(obj)) if self.metadata['RAW_VALUES'] \
                        else b'str\x00' + helpers['bstr_from_str'](repr(obj))  # ...just represent it as a string

        # Valtable+Body
        for key in self.db:
            # Note that non-string keys will be stored as string keys!
            match self.metadata['DB_INDEX_TYPE']:
                case 1:
                    body_segment = to_bytes(self.db[key])
                    valtable += (helpers['bstr_from_int'](                    len(body), unsigned=True) \
                               + helpers['bstr_from_int'](len(body_segment) + len(body), unsigned=True) \
                               + helpers['bstr_from_str'](str(key)) + b'\x00')
                case 2:
                    valtable += (helpers['bstr_from_long'](len(body), unsigned=True)
                               + helpers['bstr_from_str'] (str(key)) + b'\x00')
                    body_segment = to_bytes(self.db[key])
            body += body_segment
        print(self.db)  # debug
        self.update_metadata('VALTABLE_LEN', len(valtable))

        # Metadata
        metadata = list(self.magic) + [0 for x in range(64 - len(self.magic))]
        metadata[8], metadata[9:13], metadata[13], metadata[14] = self.metadata['VER'], \
            self.__helpers(which='bstr_from_int')(self.metadata['VALTABLE_LEN'], unsigned=True), \
            self.metadata['DB_INDEX_TYPE'], self.metadata['RAW_VALUES']
        metadata = bytes(metadata)

        return metadata + valtable + body

    def update_db(self, key, value):
        """Updates the __database key `key` with the value `value` and returns the changed key:value pair."""
        self.database.update({key: value})
        return {key: value}

    def update_metadata(self, property, value):
        """Updates the metadata key `key` with the value `value` and returns the changed key:value pair."""
        self.metadata.update({property: value})
        return {property: value}

    def __repr__(self):
        """Returns a reusable string representation of the L2DB object."""
        return f'L2DB(source={self.create_db()})'

    def __str__(self):
        """Returns a nice and short string representation of the L2DB object."""
        return f"<L2DB object from file '{self.__source_file}'>"

    def __len__(self):
        """Returns the amount of key:value pairs stored in the L2DB object."""
        return len(self.db)

    def __getitem__(self, item):
        """Gets the __database dict's value corresponding to the key `key`."""
        return self.db[item]

    def __setitem__(self, key, value):
        """Sets the __database dict's value corresponding to the key `key` to the value `value`."""
        self.db[key] = value
        return self.db[key]

    def __iter__(self):
        """The __database dict's __iter__ method."""
        return self.db.__iter__()

    def __bytes__(self):
        """Returns a byte-string with the current status of the L2DB object in it."""
        return self.create_db()

    def __add__(self, other):
        """Concatenates the L2DB with another L2DB or dict and returns the result."""
        new_l2db = L2DB(source=b'', ign_corrupted_source=True)
        new_l2db.db.update(self.db)
        new_l2db.db.update(self.__helpers(which='ret_as_dict')(other))
        return new_l2db

    def __sub__(self, other):
        """Removes all keys found in `other` from the L2DB object and returns the result."""
        new_l2db = L2DB(source=b'', ign_corrupted_source=True)
        new_l2db.db = {key: self.db[key] for key in self.db if key in
                       (self.__helpers(which='ret_as_dict')(other))}
        return new_l2db

    def __radd__(self, other):
        """Concatenates another L2DB or dict with the L2DB and returns the result."""
        return self + other

    def __rsub__(self, other):
        """Removes all keys found in `other` from the L2DB object and returns the result."""
        return self - other

    def __iadd__(self, other):
        """Concatenates the L2DB with another L2DB or dict and stores and returns the result."""
        self.db = (self + other).db
        return self

    def __isub__(self, other):
        """Removes all keys found in `other` from the L2DB object andstores and returns the result."""
        self.db = (self - other).db
        return self

    def __hex__(self):
        """Returns a hexadecimal representation of a byte-string containing the current state of the L2DB object."""
        return f"0x{''.join([hex(b)[2] for b in self.create_db()])}"

    def __oct__(self):
        """Returns a octal representation of a byte-string containing the current state of the L2DB object."""
        return oct(int(self))

    def __int__(self):
        """Returns a decimal representation of a byte-string containing the current state of the L2DB object."""
        return int(hex(self))

    def __pos__(self):
        """Returns a decimal representation of a byte-string containing the current state of the L2DB object."""
        return int(self)

    def __neg__(self):
        """Returns a negated decimal representation of a byte-string containing the current state of the L2DB object."""
        return -int(self)

    def __eq__(self, other):
        """Checks for equality of the L2DB object and another or dict and returns the result."""
        return self.db == (self.__helpers(which='ret_as_dict')(other))

    def __ne__(self, other):
        """Checks for unequality of the L2DB object and another or dict and returns the result."""
        return not self == other

    def __lt__(self, other):
        """Checks if the L2DB object has less keys in it than the other or dict and returns the result."""
        return len(self.db) < len(self.__helpers(which='ret_as_dict')(other))

    def __gt__(self, other):
        """Checks if the L2DB object has more keys in it than the other or dict and returns the result."""
        return len(self.db) > len(self.__helpers(which='ret_as_dict')(other))

    def __le__(self, other):
        """Checks if the L2DB object has less or equally many keys in it as/than the other or dict \
and returns the result."""
        return len(self.db) <= len(self.__helpers(which='ret_as_dict')(other))

    def __ge__(self, other):
        """Checks if the L2DB object has more or equally many keys in it as/than the other or dict \
and returns the result."""
        return len(self.db) >= len(self.__helpers(which='ret_as_dict')(other))

    def __contains__(self, item):
        """Returns True if the key `item` is found in the L2DB, otherwise False."""
        return item in self.db

    def __copy__(self):
        """Returns a fresh copy of the current state of the L2DB object."""
        return L2DB(source=self.create_db())

    def __deepcopy__(self, memodict={}):
        """Returns a fresh copy of the current state of the L2DB object. Ignores the argument memodict."""
        return self.copy()


if __name__ == '__main__':
    try:
        db = L2DB({'hello':'world','key':'value','some number':42,'Does bool exist?':True})
        print(f'db =           {db}\ndb.metadata =  {db.metadata}\ndb.__database =  {db.database}')
        print(f'db2 =          {(db2:=L2DB(db.create_db()))}\ndb.metadata =  {db.metadata}\ndb2.__database = {db2.database}')
    except Exception as e:
        print('''Could unfortunately not demo the __database functionality!
The following technical mumbo jumbo should show what went wrong:''')
        from traceback import format_exc as show_last_traceback

        print(show_last_traceback())
