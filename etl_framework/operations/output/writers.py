"""
Operations for writing data to file
"""
from etl_framework.operations import BaseOperation
import os, gzip, sys, logging

log = logging.getLogger(__name__)


class BaseFileWriter(BaseOperation):
    """
    Base class for a file writer, takes file content and writes to some destination
    File content can be binary or text, depending on output generator
    Output file path can either be provided during initialisation, or as keyword argument when operation is called
    (use MapArguments operation to provide extra argument)
    """
    calling_translations = {'file_data': 'output'}

    def __init__(self, output_path=None):
        """

        :param str output_path: Output file path
        """
        self.output_path = output_path

    def __call__(self, file_data, output_path=None):
        """
        Write file content to destination (can be for local filesytem, network filesystem, HDFS, String.IO buffer, etc)
        :return:
        """
        output_path = output_path or self.output_path
        if not output_path:
            self.error(ValueError, 'Output file path not provided during initialisation or execution')
        self.write_data(file_data, output_path)
        self.verify(output_path)
        return self.get_return_value(output_path)

    def write_data(self, file_data, output_path):
        """
        Write file data to path
        :param file_data:
        :param output_path:
        :return:
        """
        raise NotImplementedError()

    def verify(self, output_path):
        """
        Verify that output file has been written succesfully
        :return:
        """
        pass

    def get_return_value(self, output_path):
        """
        Get return value for FileOutputGenerator relating to output file
        :return:
        """
        raise NotImplementedError()

    def __str__(self):
        """
        Return string representation of output path
        :return:
        """
        raise NotImplementedError()


class LocalFileWriter(BaseFileWriter):
    """
    Writer for writing to local filesystem
    Provide with file data (either string or binary)
    Automatically creates any required output directories
    Returns output file path
    """

    def __init__(self, output_path=None, newline='', compress=None, append=False):
        """

        :param str output_path: output file path
        :param str newline: Newline character. Set to blank to avoid extra line terminators. Only valid for text data
        :param bool compress: Whether to write file as compressed GZIP archive. Use None to infer
        If not specified, will infer from filename (True if ends in .gz)
        :param bool append: whether to append to output file

        """
        super().__init__(output_path=output_path)
        self.newline = newline
        # Guess compression setting based on filename
        if compress is None:
            compress = output_path.endswith('.gz')
        self.compress = compress
        self.append = append

    def write_data(self, file_data, output_path):
        # Create output directory if not exists (and absolute path provided)
        dir_name = os.path.dirname(output_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Determine write mode and newline parameter
        mode = 'a' if self.append else 'w'

        if isinstance(file_data, str):
            mode += 't'
            newline = self.newline
        elif isinstance(file_data, (bytes, bytearray)):
            mode += 'b'
            newline = None
        else:
            self.error(ValueError, 'Input data must be string or bytes')

        # Get file object
        if self.compress:
            file = gzip.open(output_path, mode=mode, newline=newline)
        else:
            file = open(output_path, mode=mode, newline=newline)

        # Write content to file
        with file as f:
            f.write(file_data)

    def verify(self, output_path):
        if not os.path.isfile(output_path):
            self.error(FileNotFoundError, 'Failed to write file at: {}'.format(output_path))

    def get_return_value(self, output_path):
        return output_path

    def __str__(self):
        str = 'Write file'
        if self.output_path:
            str += ' at: {}'.format(self.output_path)
        return str


class HDFSFileSystemWriter(BaseFileWriter):
    """
    Writer to write file content to HDFS file system
    """

    def __init__(self, url, user, path=None, encoding='infer', overwrite=False):
        """

        :param url: HDFS Namenode url
        :param path: Full path to file to write (directory and filename)
        :param user: User to connect to HDFS as
        :param encoding: Encoding to apply to input data to convert to binary (set to None if binary data is provided)
        :param overwrite: Whether to overwrite existing files
        """
        from hdfs import InsecureClient
        super().__init__(output_path=path)
        self.client = InsecureClient(url, user, timeout=1)
        self.url = url
        self.encoding = encoding
        self.overwrite = overwrite
        log.debug('Connecting to HDFS node: {} as user: {}'.format(url, user))

    def write_data(self, file_data, output_path):
        # If file already exists, delete first to avoid error
        if self.client.status(output_path, strict=False):
            if self.overwrite:
                log.warning('File: {} already exists on HDFS, removing before writing new file'.format(output_path))
                self.client.delete(output_path)
            else:
                self.error(FileExistsError, 'File already exists at path: {}'.format(output_path))
        log.debug('Writing file to HDFS path: {}'.format(output_path))
        # Guess encoding to use based on file data type
        if self.encoding == 'infer':
            if isinstance(file_data, str):
                encoding = 'utf-8'
            else:
                encoding = None
        else:
            encoding = self.encoding
        self.client.write(output_path, data=file_data, encoding=encoding)

    def get_return_value(self, output_path):
        # Get return value of where file was written
        return '{}:{}'.format(self.url, output_path)

    def verify(self, output_path):
        """
        Verify file was written successfully
        :return:
        """
        if not self.client.status(output_path, strict=False):
            self.error(FileNotFoundError, 'Failed to write file on HDFS at: {}'.format(output_path))

    def __str__(self):
        str = 'Write file to HDFS'
        if self.output_path:
            str += ' at {}:{}'.format(self.url, self.output_path)
        return str


class STDOUTWriter(BaseOperation):
    """
    Write data to STDOUT
    Binary input will be written as binary output, text input as text output
    """

    calling_translations = {'file_data': 'output'}

    def __call__(self, data):
        if isinstance(data, bytes):
            sys.stdout.buffer.write(data)
        else:
            sys.stdout.write(data)

    def __str__(self):
        return 'Write data to STDOUT'