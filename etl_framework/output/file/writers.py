import os, gzip
from hdfs import InsecureClient
import logging
log = logging.getLogger(__name__)


class OutputWriter(object):
    """
    Base class for a file output writer interface
    Responsible for defining the filename and location of file
    must return a file writer object when called
    Will be re-initialised for each individual file to be written
    """

    def __call__(self):
        """
        Return writer object (can be for local filesytem, network filesystem, HDFS, String.IO buffer, etc)
        :return:
        """
        raise NotImplementedError()

    def get_return_value(self):
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


class LocalFilesystemWriter(OutputWriter):
    """
    Writer for writing to local filesystem
    Provide with output path, and automatically creates any required directories
    """

    def __init__(self, output_path, mode='wt', newline='', compress=None):
        """

        :param str output_path: output file path
        :param str mode: Open mode
        :param str newline: Newline character. Set to blank to avoid extra line terminators
        :param bool compress: Whether to write file as compressed GZIP archive.
        If not specified, will infer from filename (True if ends in .gz)
        """
        self.output_path = output_path
        self.mode = mode
        self.newline = newline
        if compress is None:
            compress = output_path[-3:] == '.gz'
        self.compress = compress

    def __call__(self):
        # Create output directory if not exists (and absolute path provided)
        dir_name = os.path.dirname(self.output_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        # Return writer
        if self.compress:
            return gzip.open(self.output_path, mode=self.mode, newline=self.newline)
        else:
            return open(self.output_path, mode=self.mode, newline=self.newline)

    def get_return_value(self):
        return self.output_path

    def __str__(self):
        return self.output_path


class HDFSFileSystemWriter(OutputWriter):
    """
    Writer to write file to HDFS file system
    """

    def __init__(self, url, path, user, encoding='utf-8', overwrite=False):
        """

        :param url: HDFS Namenode url
        :param path: Full path to file to write (directory and filename)
        :param user: User to connect to HDFS as
        :param encoding: Encoding to apply to input data to convert to binary (None if binary data being written)
        :param overwrite: Whether to overwrite existing files
        """
        self.client = InsecureClient(url, user, timeout=1)
        self.path = path
        self.url = url
        self.encoding = encoding
        self.overwrite = overwrite
        log.debug('Connecting to HDFS node: {} as user: {}'.format(url, user))

    def get_return_value(self):
        # Get return value of where file was written
        self.verify()
        return '{}:{}'.format(self.url, self.path)

    def verify(self):
        """
        Verify file was written successfully
        :return:
        """
        if not self.client.status(self.path, strict=False):
            raise FileNotFoundError('Failed to write file on HDFS at: {}'.format(self.path))

    def __call__(self):
        # If file already exists, delete first to avoid error
        if self.client.status(self.path, strict=False):
            if self.overwrite:
                log.warning('File: {} already exists on HDFS, removing before writing new file'.format(self.path))
                self.client.delete(self.path)
            else:
                raise FileExistsError('File already exists at path: {}'.format(self.path))
        log.debug('Writing file to HDFS path: {}'.format(self.path))
        return self.client.write(self.path, encoding=self.encoding)

    def __str__(self):
        return '{}:{}'.format(self.url, self.path)