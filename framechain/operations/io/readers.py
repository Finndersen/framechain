"""
Operations which read a file and produce binary file contents
"""
from framechain.operations import Operation
import gzip, sys, zlib, io


class LocalFileReader(Operation):
    """
    Standard file reader for compressed or uncompressed files.
    Takes file path, returns file reader object opened in binary or text mode
    """

    def __init__(self, gzipped=None, binary=False, **open_kwargs):
        """

        :param gzipped: Whether file is gzipped (will determine automatically if None)
        :param bool binary: Whether to read file data as binary
        :param open_kwargs:
        """
        super().__init__()
        self.gzipped = gzipped
        self.binary = binary
        self.open_kwargs = open_kwargs

    def action(self, file_path):
        mode = 'rb' if self.binary else 'rt'

        # Determine file open function
        if self.gzipped or (self.gzipped is None and file_path.endswith('.gz')):
            open_func = gzip.open
        else:
            open_func = open

        return open_func(file_path, mode=mode, **self.open_kwargs)


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


class BinaryToTextIO(Operation):
    """
    Wraps a binary file reader object as a Text IO reader
    """
    def __init__(self, encoding=None):
        """

        :param str encoding:
        """
        super().__init__()
        self.encoding = encoding

    def action(self, binary_reader):
        return io.TextIOWrapper(binary_reader, encoding=self.encoding)


class GzipFileReader(Operation):
    """
    Wraps a binary file reader object containing gzipped binary data, returns Gzip binary Reader
    """
    def action(self, binary_reader):
        return gzip.GzipFile(fileobj=binary_reader)