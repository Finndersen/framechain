"""
Operations which read a file and produce binary file contents
"""
from etl_framework.operations import Operation
import gzip, sys, zlib, io


class LocalFileReader(Operation):
    """
    Standard file reader for compressed or uncompressed files.
    Takes file path, returns file reader object opened in binary or text mode
    """
    COMPRESSION_TYPES = {
        '.gz': 'gzip'
    }

    calling_translations = {'input': 'file_reader'}

    def __init__(self, compression=None, binary=False, **open_kwargs):
        """

        :param compression: File compression ('gzip', False, or None to auto-detect)
        :param bool binary: Whether to read file data as binary
        :param open_kwargs:
        """
        super().__init__()
        if compression and compression not in self.COMPRESSION_TYPES.values():
            self.error(ValueError, 'Supported compression types are: {}'.format(self.COMPRESSION_TYPES))
        self.compression = compression
        self.binary = binary
        self.open_kwargs = open_kwargs

    def action(self, file_path):
        mode = 'rb' if self.binary else 'rt'

        # Determine compression
        if self.compression is None:
            for ext, comp in self.COMPRESSION_TYPES.items():
                if file_path.endswith(ext):
                    compression = comp
                    break
            else:
                compression = False
        else:
            compression = self.compression

        if compression == 'gzip':
            file = gzip.open(file_path, mode=mode, **self.open_kwargs)
        else:
            file = open(file_path, mode=mode, **self.open_kwargs)
        return file


class STDINReader(Operation):
    """
    Reads content from STDIN
    Requires no input value, returns stdin reader in text or binary mode
    """

    calling_translations = {'input': 'file_reader'}

    def __init__(self, binary=False):
        """

        :param bool binary: Whether to read STDIN as binary
        """
        super().__init__()
        self.binary = binary

    def action(self):
        if self.binary:
            return sys.stdin.buffer
        else:
            return sys.stdin

    def description(self):
        return 'Read data from STDIN'


class Read(Operation):
    """
    Reads content from a file object and closes it after
    """
    def __init__(self, close=True):
        """

        :param bool close: Whether to close file object after reading content
        """
        super().__init__()
        self.close = close

    def action(self, file_reader):
        content = file_reader.read()
        if self.close:
            file_reader.close()
        return content


class BytesReader(Operation):
    """
    Takes binary input and wraps in io.BytesIO to produce reader object
    """
    def action(self, binary_data):
        return io.BytesIO(binary_data)


class TextReader(Operation):
    """
    Takes text input and wraps in io.StringIO to produce reader object
    """
    def action(self, string_data):
        return io.StringIO(string_data)


class DecompressData(Operation):
    """
    Decompress binary data, zipped using GZIP, ZLIB or DEFLATE formats
    """
    COMPRESS_FORMATS = {
        'deflate': -zlib.MAX_WBITS,
        'zlib': zlib.MAX_WBITS,
        'gzip': zlib.MAX_WBITS | 16
    }

    def __init__(self, format='gzip'):
        """

        :param str format: Compression format (GZIP, ZLIB, DEFLATE)
        """
        super().__init__()
        if format not in self.COMPRESS_FORMATS:
            self.error(ValueError, 'Compression format must be one of: {}'.format(list(self.COMPRESS_FORMATS.keys())))
        self.format = format

    def action(self, compressed_data):
        return zlib.decompress(compressed_data, self.COMPRESS_FORMATS[self.format])
