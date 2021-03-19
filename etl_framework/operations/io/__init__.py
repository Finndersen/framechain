"""
Operations which take an input from an external source (e.g. file, database, API..) and present in format to be used by other operations
"""
from .readers import LocalFileReader, STDINReader, Read, DecompressData, BytesReader, TextReader
from .writers import STDOUTWriter, LocalFileWriter, HDFSFileSystemWriter