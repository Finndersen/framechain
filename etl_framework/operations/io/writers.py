"""
Operations for writing data to file
"""
from etl_framework.operations import Operation
import os, gzip, sys, logging

log = logging.getLogger(__name__)


class BaseFileWriter(Operation):
    """
    Base class for a file writer, takes file content and writes to some destination
    File content can be binary or text, depending on output generator
    """

    def __init__(self, output_path):
        """

        :param str output_path: Output file path
        """
        super().__init__()
        self.output_path = output_path

    def action(self, file_data):
        """
        Write file content to destination (can be for local filesytem, network filesystem, HDFS, String.IO buffer, etc)
        :return:
        """
        self.write_data(file_data)
        self.verify()
        return self.get_return_value()

    def write_data(self, file_data):
        """
        Write file data to path
        :param file_data:
        :param output_path:
        :return:
        """
        raise NotImplementedError()

    def verify(self):
        """
        Verify that output file has been written succesfully
        :return:
        """
        pass

    def get_return_value(self):
        """
        Get return value for FileOutputGenerator relating to output file
        :return:
        """
        raise NotImplementedError()

    def description(self):
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

    def __init__(self, output_path, newline='', compress=None, append=False, overwrite=True):
        """

        :param str output_path: output file path
        :param str newline: Newline character. Set to blank to avoid extra line terminators. Only valid for text data
        :param bool/int compress: Whether to write file as compressed GZIP archive. Use None to infer from output path.
        Can provide a number (1-9) to set compression level
        If not specified, will infer from filename (True if ends in .gz)
        :param bool append: whether to append to output file
        :param bool overwrite: Whether to overwrite existing file

        """
        super().__init__(output_path=output_path)
        self.newline = newline
        # Guess compression setting based on filename
        if compress is None:
            compress = output_path.endswith('.gz')
        self.compress = compress
        self.append = append
        self.overwrite = overwrite

    def write_data(self, file_data):
        # Create output directory if not exists (and absolute path provided)
        dir_name = os.path.dirname(self.output_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Determine write mode and newline parameter
        if self.append:
            mode = 'a'
            write_path = self.output_path
        else:
            mode = 'w'
            write_path = self.output_path + '.tmp'

        if isinstance(file_data, str):
            mode += 't'
            newline = self.newline
        elif isinstance(file_data, (bytes, bytearray)):
            mode += 'b'
            newline = None
        else:
            self.error(ValueError, 'Input data must be string or bytes')

        # Delete existing file if overwrite enabled
        if os.path.isfile(self.output_path):
            if self.overwrite:
                os.remove(self.output_path)
            else:
                raise FileExistsError('File already exists: {}'.format(self.output_path))

        # Write to temporary filename and rename when finished
        if self.compress:
            file = gzip.open(write_path, mode=mode, newline=newline,
                             compresslevel=self.compress if isinstance(self.compress, int) else 9)
        else:
            file = open(write_path, mode=mode, newline=newline)

        with file as f:
            f.write(file_data)

        try:
            os.rename(write_path, self.output_path)
        except OSError:
            self.error(FileNotFoundError, 'Failed to write file at: {}'.format(self.output_path))

    def get_return_value(self):
        return self.output_path

    def description(self):
        return 'Write file at: {}'.format(self.output_path)


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
        # Import here so only needed when operation is usec
        from hdfs import InsecureClient
        super().__init__(output_path=path)
        self.client = InsecureClient(url, user, timeout=1)
        self.url = url
        self.encoding = encoding
        self.overwrite = overwrite
        log.debug('Connecting to HDFS node: {} as user: {}'.format(url, user))

    def write_data(self, file_data):
        # If file already exists, delete first to avoid error
        if self.client.status(self.output_path, strict=False):
            if self.overwrite:
                log.warning('File: {} already exists on HDFS, removing before writing new file'.format(self.output_path))
                self.client.delete(self.output_path)
            else:
                self.error(FileExistsError, 'File already exists at path: {}'.format(self.output_path))
        log.debug('Writing file to HDFS path: {}'.format(self.output_path))
        # Guess encoding to use based on file data type
        if self.encoding == 'infer':
            if isinstance(file_data, str):
                encoding = 'utf-8'
            else:
                encoding = None
        else:
            encoding = self.encoding
        self.client.write(self.output_path, data=file_data, encoding=encoding)

    def get_return_value(self):
        # Get return value of where file was written
        return '{}:{}'.format(self.url, self.output_path)

    def verify(self):
        """
        Verify file was written successfully
        :return:
        """
        if not self.client.status(self.output_path, strict=False):
            self.error(FileNotFoundError, 'Failed to write file on HDFS at: {}'.format(self.output_path))

    def description(self):
        return 'Write file to HDFS at {}:{}'.format(self.url, self.output_path)


class STDOUTWriter(Operation):
    """
    Write data to STDOUT
    Binary input will be written as binary output, text input as text output
    """

    calling_translations = {'file_data': 'output'}

    def action(self, data):
        if isinstance(data, bytes):
            sys.stdout.buffer.write(data)
        else:
            sys.stdout.write(data)

    def description(self):
        return 'Write data to STDOUT'