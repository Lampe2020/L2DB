# L2DB file format specification
*If you want to make an alternative implementation of this format, use this document as a reference to ensure compatibility.*   
- Version 0.1   
- Copyright (c) by Lampe2020 <kontakt@lampe2020.de>   
- "spec", "the spec" or "this spec" in the following document refer to this specification unless otherwise specified.   
- If the data is stored in a file it should (but doesn't need to) have either the `.dat` or the `.l2db` file extension.
- The class name in the implementation should be `L2DB`, if several versions are supported `L2DBVer{{version}}`.   
- *Please note that this specification is written with Python3 in mind, if e.g. built-in functions or error types are 
mentioned you may replace them with your programming language's equivalent.*   

## Structure
All integers in L2DB are little-endian (the least significant bit comes last, 
e.g. 2048 is split up into `0x08 0x00` and not `0x00 0x08`).    
All strings in L2DB are UTF-8 encoded.   
The file is made of three sections, which are the [header](#header) (with a length of 64 bytes), the 
[index](#index) (with variable length) and the [data](#data) (with variable length). 

### Header
The header (with the file magic included) is always 64 bytes long, with the non-used bytes being filled with 
`null`-bytes (`\0`), although this doesn't need to be enforced.   

| Offset *(ranges include both start and end)* |   Meaning    | Content                                                                       | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|:--------------------------------------------:|:------------:|:------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|                     0-7                      |  File magic  | bytes([0x88, 0x4c, 0x32, 0x44, 0x42, 0x00, 0x00, 0x00]) (`b'\x88L2DB\0\0\0'`) | Allows for easy recognition of the file as an L2DB file.                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                     8-11                     | Spec version | The spec version as one `float`                                               | The version[^1] of the standard used to create the file. If this doesn't match the implementation's version the implementation should convert the in-memory copy of the file to the matching version if possible, otherwise raise a `L2DBVersionMismatch` exception with the message `The database follows the spec version {{db_ver}} but the implementation follows the spec version {{imp_ver}}. Conversion failed.`, with `db_ver` being the database's version and `imp_ver` being the implementation's version. |
|                    12-15                     | Index length | one `uint32`                                                                  | The length of the [index](#index).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|                      16                      |    Flags     | *See flag table below.*                                                       | If all flags are set the byte should have the value 0x83 (`0b10000011`).                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                    17-63                     |     none     | *Not assigned yet.*                                                           | Should be filled with`null`-bytes (`\0`). Strict implementations should set the `DIRTY` flag if this is not the case.                                                                                                                                                                                                                                                                                                                                                                                                 |

|   Flag name   |    Flag position    | Flag meaning                                                                                                                                                                                                                                                                                                       |
|:-------------:|:-------------------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|   *unused*    | Byte 14<br>Bits 0-4 | none *Note: strict implementations should automatically reset these if they happen to be set.*                                                                                                                                                                                                                     |
|   `LOCKED`    |  Byte 14<br>Bit 5   | The database can only be opened in ['rf' mode](#modes) and each reading action will cause a warning that the database is locked.                                                                                                                                                                                   |
|    `DIRTY`    |  Byte 14<br>Bit 6   | If any error occurs during reading/writing on the DB this bit gets set.<br>If it is set, each subsequent reading action will cause a warning that the database is dirty and each writing action on the database will fail and raise a `L2DBIsDirty` exception  until the [`cleanup()`](#cleanup) method is called. |
| `X64_INDEXES` |  Byte 14<br>Bit 7   | If the index numbers are one `uint64` or two `uint32`s                                                                                                                                                                                                                                                             |

### Index
The index is a long string of entries which give a specific part of the data block a name and type. 
The length of this string is specified by the 8 bytes for the index number(s) followed by three non-`null` bytes 
for the value type and a variable amount of non-`null` bytes for the name which is terminated by one `null`-byte. 
If the type is unknown it will be interpreted as raw.   
The order of these entries does not need to be maintained but can be.   
If the flag `X64_INDEXES` is not set the index numbers will be two `uint32`s which refer to the starting and end offset 
of the value's data.   
If it is set then the index number is one `uint64` which refers to the offset where the value's data 
starts, the end index is found by getting the next value's starting index. The last value ends at the file end. 
Be aware that in this case the values can still switch order but then the offsets need to be recalculated!   
*Note: the indexed offsets are relative to the first data byte as byte 0, **not** the first byte of the file!*   

### Data
The data section is a pure concatenation of all values in the whole database. 

## Value types

|       Type name       | Identifier | Description                                                                                                                                                                                                                                                                                                        |
|:---------------------:|:----------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|     Whole number      |   `int`    | Any positive or negative 64-bit whole number. (aka.`long`[^2]) If a positive number too large for a normal `long` is tried to assign, implicitly convert the key to a `uin` and cause a warning.                                                                                                                   |
| Positive whole number |   `uin`    | Any positive 64-bit whole number. (aka.`unsigned long`[^2]) If a negative number is tried to assign, implicitly convert the key to a `int` and cause a warning.                                                                                                                                                    |
|        Number         |   `flt`    | Any positive or negative 64-bit number. (aka.`double`[^2])                                                                                                                                                                                                                                                         |
|        String         |   `str`    | Any UTF-8 encoded string.                                                                                                                                                                                                                                                                                          |
|          Raw          |   `raw`    | Any sequence of bytes.                                                                                                                                                                                                                                                                                             |
|         Empty         |   `nul`    | No value specified, gets a single `null`-byte (`\0`) in the [data](#data) section. *Note: in strict implementations the `DIRTY` bit should be set if this byte is anything other than null!*<br> If a value other than `undefined` or `null` is assigned, implicitly convert the key to the appropriate data type. |


## Modes
The database can be opened in any combination of the following modes:

| Mode |  Meaning  | Description                                                                                                                                                                                                                                                                                |
|:----:|:---------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `r`  | readable  | The database can be read.                                                                                                                                                                                                                                                                  |
| `w`  | writeable | The database can be written to. This implicitly half-enables the `r` mode, allowing for the program to orient itself but not for any read methods to work.<br>*Note: If this is used without `f` mode the changes are only applied to the file on call to the [`flush()`](#flush) method!* |
| `f`  |   file    | The database works directly on the database file without buffering into memory. *Note: in this mode all actions are immediately applied to the file!*                                                                                                                                      |

## Methods
*The following methods are in no particular order and should all be defined if they aren't marked as optional.*

<!-- TODO: Add the remaining method descriptions! -->

### `flush()`
| Argument name | Default value | Optional? |                  Possible values                   |
|:-------------:|:-------------:|:---------:|:--------------------------------------------------:|
|   filename    |    `None`     |    Yes    | any string or binary file handle with write access |
|     move      |    `False`    |    Yes    |                    any boolean                     |

This method flushes the buffered changes to the given file 
or (if none given) to the file the database has been read from.   
If the database is in [`f` mode](#modes) this will just clone the database file to the new location, 
see [`f` mode's description](#modes).   
*Note: If no file is given and none has been used to initialize the database this method shall raise a 
`FileNotFoundError` with the message `No file specified!`!*

### `cleanup()`
| Argument name | Default value | Optional? | Possible values |
|:-------------:|:-------------:|:---------:|:---------------:|
|  `only_flag`  |    `False`    |    Yes    |   any boolean   |

If `only_flag` is True only the `DIRTY` flag will be reset but no errors will be fixed. **Warning: this may cause 
errors later on if there is invalid content in the file!**   
Otherwise the method searches for and fixes any errors in the database, such as checking wether all values are 
readable as their assigned type and if not, if they are readable as any other type, with the fallback being 'raw'. The 
[header](#header) is completely regenerated in this case.   
After the check the `DIRTY` flag is reset and (if the runtime-flag `verbose` is set) the errors and fixes are output.   


<!-- Footnotes: -->

[^1] The "version" in this case refers to a float with the whole-number part being the major version and the decimal 
part being the minor version. Any subversions of those may not introduce breaking changes so they can be omitted.   
[^2] I chose the largest type available to keep the spec simple, implementations may choose to "compress" them if their 
value fits into smaller types or simply a smaller type is needed.
