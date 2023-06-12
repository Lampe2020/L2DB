* Add from-drive working: only cache the valtable to memory, then read from the specified file the correct bytes via `file.seek(offset)` and then `file.read(length)`. 
