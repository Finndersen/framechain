"""
Operations which produce some kind of external output (write to file, insert into database, return to STDOUT..)
"""
from .writers import LocalFileWriter, HDFSFileSystemWriter, STDOUTWriter