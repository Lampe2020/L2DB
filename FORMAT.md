<!-- Old description:   
The first 64 bytes of the file are reserved for metadata, 8 of which define the value_table's length after the metadata.
The first 8 bytes are _always_ b'\\x88L2DB\\x00\\x00\\x00' or b'\\x88L2020DB'.
Length of value_table defined in 32-bit number (4 bytes) (There should never be the need for a 4GB+ big index listing!).
All indexes are beginning to be counted after that.
For example, with a value_table length of 12, the byte at real index 100 is called
index ((real_index:100)-(metadata_length:const:64)-(value_table_length=12)) = 14.
In the value_table, two 4-byte (32-bit) numbers for each value represent the start and end index of that value
(DB_INDEX_TYPE:1). The names of all values are immediately after their index and null-terminated,
up to 32 usable bytes per name. If the index is immediately followed by a null-byte the index is used as the name.
Alternatively, 8 bytes represent the index and the end is then the byte before the next index or the
file end (DB_INDEX_TYPE:2). A DB_INDEX_TYPE of 0 is invalid and as of now also anything above 2; they will default to 2.
Type declarations occur in the value itself, with ASCII-encoded type name, separated by null from the value.
To get a bstring without type declaration, just begin the value with a null character,
which will be stripped away and the resulting 0-character type declaration will cause the value
to be stored as the raw binary value.
-->

# L2DB file format specification
- version 1   
*If you want to make an alternative implementation of this format, use this as a reference.*   
Please note that this specification is written with Python3 in mind, if e.g. built-in functions or error types are 
mentioned you can replace them with your programming language's equivalent.  

## Structure
All integers in L2DB are little-endian (the least significant bit comes last, e.g. 2048 is `0b0000100000000000`).    
The file is made of three sections, which are the [header](#header) (with a length of 64 bytes), the 
[index](#index) (with variable length) and the [data](#data) (with variable length). 

### Header
The file always begins with the following eight bytes: 
0x88, 0x4c, 0x32, 0x44, 0x42, 0x00, 0x00, 0x00 (`\x88L2DB\0\0\0`), which make up the "file magic" (easy way to 
recognize an L2DB file just by its first few bytes).   
The header (with the file magic included) is always 64 bytes long, with the non-used bytes being filled with zeroes, 
although this doesn't need to be enforced.   
The bytes at offset 8-9 contain the implementation version as a `uint16`. 
If this doesn't match the program's version the program should convert the in-memory copy of the file 
to the matching version if possible, otherwise raise a `L2DBVersionMismatch` with the message 
`The database is in version {{db_ver}} but the reader is in version {{imp_ver}}. Conversion failed.`, 
with `db_ver` being the database's version and `imp_ver` being the implementation's version.
At offset 10-13 lies the [index](#index) length as an unsigned 32-bit integer.   
After that comes the first eight flags at offset 14, If all flags are set the byte has the value 0x83 (0b10000011).   
LOCKED, *unused*, *unused*, *unused*, *unused*, *unused*, DIRTY, X64_INDEXES   

| Offset |   Meaning    | Content                                                                    | Description                                          |
|:------:|:------------:|:---------------------------------------------------------------------------|:-----------------------------------------------------|
|  0-7   |  File magic  | bytes([0x88, 0x4c, 0x32, 0x44, 0x42, 0x00, 0x00, 0x00]) (`\x88L2DB\0\0\0`) | Allows for easy recognition of the file as a L2DB.   |
|  8,9   | Spec version | one `uint16`                                                               | The version of the standard used to create the file. |
| 10-13  | Index length | one `uint32`                                                               | The length of the [index](#index)                    |
|   14   |    Flags     | *See flag table below.*                                                    |                                                      |
| 15-63  |     none     | *Not assigned yet.*                                                        | Should be filled with`null`-bytes (`\0`).            |

|   Flag name   |    Flag position    | Flag meaning                                                                                                                                                                                                                                                                                                       |   
|:-------------:|:-------------------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|   `LOCKED`    |  Byte 14<br>Bit 0   | The database can only be opened in ['rf' mode](#modes) and each reading action will cause a warning that the database is locked.                                                                                                                                                                                   |   
|   *unused*    | Byte 14<br>Bits 1-5 | none                                                                                                                                                                                                                                                                                                               |
|    `DIRTY`    |  Byte 14<br>Bit 6   | If any error occurs during reading/writing on the DB this bit gets set.<br>If it is set, each subsequent reading action will cause a warning that the database is dirty and each writing action on the database will fail and raise a `L2DBIsDirty` exception  until the [`cleanup()`](#cleanup) method is called. |   
| `X64_INDEXES` |  Byte 14<br>Bit 7   | If the index numbers are one `uint64` or two `uint32`s                                                                                                                                                                                                                                                             |   

### Index
The index is a long string of entries which give a specific part of the data block a name. The length of this string is specified by the.   
8 bytes for the index number(s) followed by a variable amount of non-`null` bytes for the name which is terminated by 
one `null`-byte.   
If the flag `X64_INDEXES` is not set the index numbers will be two `uint32`s which refer to the starting and end offset 
of the value's data.   
If it is set then the index number is one `uint64` which refers to the offset where the value's data 
starts, the end index is found by getting the next value's starting index. The last value ends at the file end.   
*Note: the indexed offsets take the first data byte as byte 0, **not** the first byte of the file!*   

### Data
*coming soon*

## Value types
*coming soon*

## Modes
The database can be opened in any combination of the following modes:

| Mode |  Meaning  | Description                                                                                                                                                                                       |
|:----:|:---------:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `r`  | readable  | The database can be read.                                                                                                                                                                         |
| `w`  | writeable | The database can be written to. *Note: this requires the `r` mode!<br>Note: If this is used without `f` mode the changes are only applied to the file on call to the [`flush()`](#flush) method!* |
| `f`  |   file    | The database works directly on the database file without buffering into memory. *Note: in this mode all actions are immediately applied to the file!*                                             |

## Methods
*The following methods are in no particular order and should all be defined if they aren't marked as optional.*

### `flush()`
| Argument name | Default value | Optional? |              Possible values               |
|:-------------:|:-------------:|:---------:|:------------------------------------------:|
|   filename    |    `None`     |    Yes    | any string or binary writeable file handle |
|     move      |    `False`    |    Yes    |                any boolean                 |
This method flushes the buffered changes to the given file 
or (if none given) to the file the database has been read from.   
If the database is in [`f` mode](#modes) this will just clone the database file to the new location, 
see [`f` mode's description](#modes).   
*Note: If no file is given and none has been used to initialize the database this method will raise a 
`FileNotFoundError` (or its equivalent from the implementation's programming language)*

### `cleanup()`
| Argument name | Default value | Optional? | Possible values |
|:-------------:|:-------------:|:---------:|:---------------:|
|  `only_flag`  |    `False`    |    Yes    |   any boolean   |
If `only_flag` is True only the `DIRTY` flag will be reset but no errors will be fixed. **Warning: this may cause 
errors later on if there are errors!**   
Otherwise the method searches for and fixes any errors in the database, such as checking wether all values are 
readable as their assigned type and if not, if they are readable as any other type, with the fallback being 'raw'.   
After the check the `DIRTY` flag is reset and (if the runtime-flag `verbose` is set) the errors and fixes are output.   