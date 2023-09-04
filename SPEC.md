# L2DB file format specification
*If you want to make an alternative implementation of this format, use this document as a reference to ensure compatibility.*   
- Version 2.0.0  
- Copyright (c) by Christian Lampe <kontakt@lampe2020.de>   
- If strings in this spec contain a variable name enclosed in double curly braces this means that that part of the 
string shouldn't be taken literally but instead replaced with the appropriate content, if not specified otherwise.
- "spec", "the spec" or "this spec" in the following document refer to this specification unless otherwise specified.   
- If the data is stored in a file it should (but doesn't need to) have either the `.dat` or the `.l2db` file extension.
- The class name in the implementation should be `L2DB`, if several versions are supported `L2DBVer_{{version}}` 
  (replace `{{version}}` with the version in the format `major_minor_patch`, optionally omitting both minor and patch 
  version or only patch version).   
- File paths may be relative or absolute, the implementation must not restrict the user to usage of only absolute or 
  only relative paths.   
- *Please note that this specification is written with Python3 in mind, if e.g. built-in functions or error types are 
  mentioned you may replace them with your programming language's equivalent. For example can `dict`s be replaced with 
  associative arrays or (in JS) `Object`s.*   

# Table of contents
1. [Structure](#structure)
   1. [Header](#header)
   2. [Index](#index)
   3. [Data](#data)
2. [Value types](#value-types)
3. [Modes](#modes)
4. [Methods](#methods)
   1. [`open()`](#open)
   2. [`read()`](#read)
   3. [`write()`](#write)
   4. [`delete()`](#delete)
   5. [`convert()`](#convert)
   6. [`dump()`](#dump)
   7. [`dumpbin()`](#dumpbin)
   8. [`flush()`](#flush)
   9. [`cleanup()`](#cleanup)
5. [Error classes](#error-classes)

## Structure
All integers in L2DB are little-endian (the least significant bit comes last, 
e.g. 2048 is split up into `0x08 0x00` and not `0x00 0x08`).    
All strings in L2DB are UTF-8 encoded.   
The file is made of three sections, which are the [header](#header) (with a length of 64 bytes), the 
[index](#index) (with variable length) and the [data](#data) (with variable length). 

### Header
The header (with the file magic included) is always 64 bytes long, with the non-used bytes being filled with 
`null`-bytes (`\0`), although this doesn't need to be enforced.   

| Offset *(ranges include both start and end)* |                    Meaning                     | Content                                                                       | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|:--------------------------------------------:|:----------------------------------------------:|:------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|                     0-7                      |                   File magic                   | bytes([0x88, 0x4c, 0x32, 0x44, 0x42, 0x00, 0x00, 0x00]) (`b'\x88L2DB\0\0\0'`) | Allows for easy recognition of the file as an L2DB file.                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|            8-9<br>10-11<br/>12-13            | Spec version: <br/>major, <br>minor, <br>patch | The spec version as three unsigned `short`s                                   | The version[^1] of the standard used to create the file. If this doesn't match the implementation's version the implementation should convert the in-memory copy of the file to the matching version if possible, otherwise raise a `L2DBVersionMismatch` exception with the message `The database follows the spec version {{db_ver}} but the implementation follows the spec version {{imp_ver}}. Conversion failed.`, with `db_ver` being the database's version and `imp_ver` being the implementation's version. |
|                    14-17                     |                  Index length                  | one `uint32`                                                                  | The length of the [index](#index).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|                      18                      |                     Flags                      | *See flag table below.*                                                       | If all flags are set the byte should have the value 0x83 (`0b10000011`).                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                    19-63                     |                      none                      | *Not assigned yet.*                                                           | Should be filled with`null`-bytes (`\0`). Strict implementations should set the `DIRTY` flag if this is not the case.                                                                                                                                                                                                                                                                                                                                                                                                 |

|   Flag name   |    Flag position    | Flag meaning                                                                                                                                                                                                                                                                                                      |
|:-------------:|:-------------------:|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|   *unused*    | Byte 14<br>Bits 0-4 | none *Note: strict implementations should automatically reset these if they happen to be set.*                                                                                                                                                                                                                    |
|   `LOCKED`    |  Byte 14<br>Bit 5   | The database can only be opened in ['rf' mode](#modes) and each reading action will emit a warning that the database is locked.                                                                                                                                                                                   |
|    `DIRTY`    |  Byte 14<br>Bit 6   | If any error occurs during reading/writing on the DB this bit gets set.<br>If it is set, each subsequent reading action will emit a warning that the database is dirty and each writing action on the database will fail and raise a `L2DBIsDirty` exception  until the [`cleanup()`](#cleanup) method is called. |
| `X64_INDEXES` |  Byte 14<br>Bit 7   | If the index numbers are `uint64` or `uint32`s                                                                                                                                                                                                                                                                    |

### Index
The index is a long string of entries which give a specific part of the data block a name and type. 
The length of this string is specified in the "Index length" bytes in the [header](#header).   
Each entry consists of 8 bytes (flag `X64_INDEXES` unset, so two 32-bit `int`s) or 16 bytes (flag `X64_INDEXES` set, so 
two 64-bit `long long`s) for the index numbers followed by three non-`null` bytes for the value type and a variable 
amount of non-`null` bytes for the name which is terminated by one `null`-byte. 
If the type is unknown it will be interpreted as raw and a warning should be emitted stating `Unknown format 
{{format}}! Interpreting as 'raw'`.   
The order of these entries does not need to be maintained but can be.   
*Note: the indexed offsets are relative to the first data byte as byte 0, **not** the first byte of the file!*   

### Data
The data section is a pure concatenation of all values in the whole database. 

## Value types
*If implicit type conversions are done, emit a warning `Implicitly converted '{{old_type}}' to '{{new_type}}'`.   
If a type conversion fails or isn't possible, raise a `L2DBTypeError` exception with the message `Could not assign 
value of type '{{val_type}}' to key of type '{{key_type}}'`, with `val_type` being the value's type Identifier (see 
table below) and `key_type` being the key's type Identifier (see table below), optionally extend the message with 
` Details: {{details}}`, with `details` being any string that tries to explain the error or help to avoid it.*

|       Type name       | Identifier | Description                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|:---------------------:|:----------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|     Whole number      |   `int`    | Any positive or negative 64-bit whole number. (aka.`long`[^2]) If a positive number too large for a normal `long` is tried to assign, implicitly convert the key to a `uin` if that allows for storing the value, otherwise fail.                                                                                                                                                                                                                        |
| Positive whole number |   `uin`    | Any positive 64-bit whole number. (aka.`unsigned long`[^2]) If a negative number is tried to assign, implicitly convert the key to a `int` if that allows for storing the value, otherwise fail.                                                                                                                                                                                                                                                         |
| Floating point number |   `flt`    | Any positive or negative 64-bit number. (aka.`double`[^2]) <br>*Note that this will sooner or later be removed in favor of `fpn`*                                                                                                                                                                                                                                                                                                                        |
|  Fixed point number   |   `fpn`    | Any positive or negative 64-bit number, stored in a custom format. <br>*Note: `fpn` should currently automatically get converted to `flt` and strict implementations should emit a warning with the message `'fpn' is not implemented yet as there is no standard for it`*                                                                                                                                                                               |
|        Boolean        |   `bol`    | True or False. Is stored in a single byte which is set to either 0x01 (True) or 0x00 (False). If a `int`, `uin` or `flt` 0 or 1 or raw `null`-byte (`\0`) or one-byte (`\1`) is tried to assign, implicitly convert the value to `True` for 1 and `False` for 0. If `null` is tried to assign, implicitly convert the key to `nul`.<br>*Note: in strict implementations the `DIRTY` bit should be set if this byte is anything other than 0x00 or 0x01!* |
|        String         |   `str`    | Any UTF-8 encoded string.                                                                                                                                                                                                                                                                                                                                                                                                                                |
|          Raw          |   `raw`    | Any sequence of bytes.                                                                                                                                                                                                                                                                                                                                                                                                                                   |
|         Empty         |   `nul`    | No value specified, gets a single `null`-byte (`\0`) in the [data](#data) section. *Note: in strict implementations the `DIRTY` bit should be set if this byte is anything other than null!*<br> If a non-`null` value is assigned, implicitly convert the key to the appropriate data type if that allows for storing the value, otherwise fail.                                                                                                        |
|        Invalid        |   `inv`    | Non-storable data type, just used for error messages.                                                                                                                                                                                                                                                                                                                                                                                                    |


## Modes
The database can be opened in any combination of the following modes:

| Mode |  Meaning  | Description                                                                                                                                                                                                                                                                                |
|:----:|:---------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `r`  | readable  | The database can be read.                                                                                                                                                                                                                                                                  |
| `w`  | writeable | The database can be written to. This implicitly half-enables the `r` mode, allowing for the program to orient itself but not for any read methods to work.<br>*Note: If this is used without `f` mode the changes are only applied to the file on call to the [`flush()`](#flush) method!* |
| `f`  |   file    | The database works directly on the database file without buffering into memory. *Note: in this mode all actions are immediately applied to the file!*                                                                                                                                      |

## Methods
*The following methods are in no particular order and should all be defined if they aren't marked as optional.   
"Optional" arguments have to be implemented but don't need to be specified if the programming language supports that, 
if the programming language used for the implementation does not support optional arguments they should accept 
`undefined` (or equivalent) as "argument omitted".*

### `open()`

|  Argument name  | Default value |  Optional?   | Possible values                                                                                                                                                                                                                                                                                                       |
|:---------------:|:-------------:|:------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|    `source`     |               |      No      | File path, as String<br>- `rb`, `r+b` or `w+b` file handle<br>- `bytes` to act on as if they were the file content<br>- `dict` with zero or more valid key-value pairs, invalid pairs are tried to convert or are otherwise discarded with a warning stating `Could not load key '{{keyname}}', discarding it`.       |
|     `mode`      |    `'rw'`     |     Yes      | String with any combination of letters described in the [modes](#modes) table.                                                                                                                                                                                                                                        |
| `runtime_flags` | empty `tuple` |     Yes      | A list of strings that specify each one runtime flag name to be enabled. All runtime flags are by default disabled.                                                                                                                                                                                                   |
|                 |               | Return value | The database object that has been opened by calling this method                                                                                                                                                                                                                                                       |

This method populates the `L2DB` with the new content and (if there were more than zero keys in the `L2DB` before) 
emits a warning stating `Old content of L2DB has been discarded in favor of new content`. This method is also 
called by the object constructor to populate the database.   
If the `source` is a file handle, `mode` is ignored and taken from the file handle's `mode` attribute. If that 
is invalid for L2DB the mode is set to `'r'` and a warning is emitted stating that 
`L2DB cannot be initialized in '{{file handle's mode}}' mode!`.   

### `read()`

| Argument name | Default value |  Optional?   | Possible values                                                                                      |
|:-------------:|:-------------:|:------------:|:-----------------------------------------------------------------------------------------------------|
|     `key`     |               |      No      | Any string that occurs as a key name in the currently-opened DB                                      |
|    `vtype`    |    `None`     |     Yes      | Any three-letter [type Identifier](#value-types) that the value should be converted to after reading |
|               |    `None`     | Return value | The value of the read key                                                                            |

This method returns the value of the requested key if possible, if no type is given the data is returned as the stored 
type. If a type is given it will be converted using [`L2DB.convert()`](#convert) before returning it. Any exceptions 
raised by [`L2DB.convert()`](#convert) should not be caught.   
If the key doesn't exist, it raises a `L2DBKeyError` exception with the message `{{key}} could not be found`, with 
`key` in single quotes and any contained single quotes escaped with a backslash.   
If the key is found several times in the DB an implementation-specific one of all the values is picked (first, last or 
random).   


### `write()`

| Argument name |     Default value     |  Optional?   | Possible values                                                                                                    |
|:-------------:|:---------------------:|:------------:|:-------------------------------------------------------------------------------------------------------------------|
|     `key`     |                       |      No      | Any string that doesn't contain a `null`-byte                                                                      |
|    `value`    |                       |      No      | Any value storable in an L2DB format                                                                               |
|    `vtype`    |        `None`         |     Yes      | Any three-letter [type Identifier](#value-types) that the stored value should be converted to before writing       |
|               | `{'key':'','val':''}` | Return value | A `dict` with the keys `key` and `val` which contains the given key and value as if they had been read from the DB |

This method stores any value given to it into the database with the key provided to it.   
If a specific type is given the values is converted to 

### `delete()`

| Argument name |     Default value     |  Optional?   | Possible values                                                                                             |
|:-------------:|:---------------------:|:------------:|:------------------------------------------------------------------------------------------------------------|
|     `key`     |                       |      No      | Any string that matches an existing key stored in the DB                                                    |
|               | `{'key':'','val':''}` | Return value | A `dict` with the keys `key` and `val` which contains the given key and value as they were stored in the DB |

Removes the given key along with its value from the DB.   
If the key doesn't exist, it raises a `L2DBKeyError` exception with the key as an argument.   


### `convert()`

| Argument name | Default value |  Optional?   | Possible values                                                                               |
|:-------------:|:-------------:|:------------:|:----------------------------------------------------------------------------------------------|
|     `key`     |               |      No      | Any string matching a key's name or (if `fromval` is set) an empty string                     |
|    `vtype`    |               |      No      | Any three-letter string matching one of the type Identifiers (see [type table](#value-types)) |
|   `fromval`   |    `None`     |     Yes      | Any value representable as one of the [L2DB-compatible types](#value-types)                   |
|               |               | Return value | The converted value                                                                           |

Converts the key along with its value to the target type, if that fails a `L2DBTypeError` exception should be raised 
with the `key` name and `vtype` as arguments and if `fromval` is set `key` should be `None`.   
If `fromval` is set the given `key` name is ignored and the value to convert is taken from `fromval` instead of the DB.   
If a `flt` is converted to any whole number type it simply loses its decimals (not rounded but cut off) and if any 
whole number type is converted to `flt` it gets 0 as the only decimal place. Examples: `1.999 -> 1`, `-3.7 -> 3` and 
`1 -> 1.0`   
If a negative number gets converted to `uin` it loses its negativity and if a `uin` that's too large for `int` gets 
converted to `int` it is set to 4294967295 (0xffffffff). Examples: `-3 -> 3`, `-2.9 -> 2` and `4294967296 -> 
4294967295`.


### `dump()`

| Argument name | Default value |  Optional?   | Possible values                         |
|:-------------:|:-------------:|:------------:|:----------------------------------------|
|               | empty `dict`  | Return value | A `dict` containing all keys and values |

If a key is found several times in the DB an implementation-specific one of all the values is picked (first, last or 
random, the implementer decides which one).   

### `dumpbin()`

| Argument name | Default value |  Optional?   | Possible values                                                                  |
|:-------------:|:-------------:|:------------:|:---------------------------------------------------------------------------------|
|               | empty `bytes` | Return value | A `bytes` object that contains the database as if it had been written to a file. |

Same as [`dump()`](#dump) but in binary form.  


### `flush()`
| Argument name | Default value |  Optional?   | Possible values                                                                   |
|:-------------:|:-------------:|:------------:|:----------------------------------------------------------------------------------|
|    `file`     |    `None`     |     Yes      | any string which is a valid file path or file handle in `wb`, `r+b` or `w+b` mode |
|    `move`     |    `False`    |     Yes      | any boolean                                                                       |
|               |               | Return value |                                                                                   |

This method flushes the buffered changes to the given file 
or (if none given) to the file the database has been read from.   
If the database is in [file mode](#modes) this will just clone the database file to the new location, 
see the [file mode's description](#modes).   
*Note: If no file is given and none has been used to initialize the database this method shall raise a 
`FileNotFoundError` with the message `No file specified`!*

### `cleanup()`
| Argument name | Default value |  Optional?   | Possible values                                                                   |
|:-------------:|:-------------:|:------------:|:----------------------------------------------------------------------------------|
|  `only_flag`  |    `False`    |     Yes      | any boolean                                                                       |
| `dont_rescue` |    `False`    |     Yes      | any boolean                                                                       |
|               |               | Return value | A `dict` with the error message strings as keys and fix message strings as values |

If `only_flag` is `True` only the `DIRTY` flag will be reset but no errors will be fixed. **Warning: this may cause 
errors later on if there is invalid content in the file!**   
Otherwise the method searches for and fixes any errors in the database, such as checking wether all values are 
readable as their assigned type and if not, if they are readable as any other type, with the fallback being 'raw'. The 
[header](#header) is completely regenerated in this case. If `dont_rescue` is set to `True` all invalid values are 
discarded instead of being tried to fix and the [header](#header) is regenerated.   
After the check the `DIRTY` flag is reset and (if the runtime-flag `verbose` is set) the errors and fixes are logged.   


## Error classes

|      Error name       | Default message                                                                                                    | Explanation                                                                                                                                                              |
|:---------------------:|:-------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|      `L2DBError`      | empty string                                                                                                       | Base error type, base class for all other L2DB errors to inherit from                                                                                                    |
| `L2DBVersionMismatch` | `database follows spec version {{db_ver}} but implementation follows spec version {{imp_ver}}. Conversion failed.` | `db_ver` is the `major.minor` version of the spec that the database file follows and `imp_ver` is the `major.minor` version of the spec that the implementation follows. |
|    `L2DBTypeError`    | `Could not convert key '{{keyname}}' to type '{{type}}'` or `Could not convert value to type '{{type}}'`           | `keyname` is the name of the key tried to convert (if it contains single quotes they should be escaped with backslashes) and `type` is the target type.                  |
|    `L2DBKeyError`     | `Key '{{key}}' could not be found`                                                                                 | `key` is the name of the key that could not be found (if it contains single quotes they should be escaped with backslashes).                                             |



<!-- Footnotes: -->

[^1] The "version" in this case refers to a float with the whole-number part being the major version and the decimal 
part being the minor version. As I try to follow [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html) the patch version 
can be omitted.   
[^2] I chose the largest type available to keep the spec simple, implementations may choose to "compress" them if their 
value fits into smaller types or simply a smaller type is needed.
