"""
Operations which read a file and produce binary file contents
"""
from etl_framework.operations import BaseOperation
import gzip, sys


class LocalFileReader(BaseOperation):
    """
    Standard file reader for compressed or uncompressed files.
    Takes file path, Reads file and returns content as either bytes or string, depending on read_mode
    """
    COMPRESSION_TYPES = {'gzip'}

    calling_translations = {'input': 'file_data'}

    def __init__(self, compression=None, binary=False, **open_kwargs):
        """

        :param compression: File compression ('gzip' or None)
        :param bool binary: Whether to read file data as binary
        :param open_kwargs:
        """
        if compression and compression not in self.COMPRESSION_TYPES:
            self.error(ValueError, 'Supported compression types are: {}'.format(self.COMPRESSION_TYPES))
        self.compression = compression
        self.binary=binary
        self.open_kwargs = open_kwargs

    def __call__(self, file_path):
        mode = 'rb' if self.binary else 'rt'
        if self.compression == 'gzip':
            file = gzip.open(file_path, mode=mode, **self.open_kwargs)
        else:
            file = open(file_path, mode=mode, **self.open_kwargs)
        return file.read()


class STDINReader(BaseOperation):
    """
    Reads content from STDIN
    Requires no input value, returns value either as text string or binary (byte string)
    """

    calling_translations = {'input': 'file_data'}

    def __init__(self, binary=False):
        """

        :param bool binary: Whether to read STDIN as binary
        """
        self.binary = binary

    def __call__(self, *args, **kwargs):
        if self.binary:
            return sys.stdin.buffer.read()
        else:
            return sys.stdin.read()

    def __str__(self):
        return 'Read data from STDIN'
