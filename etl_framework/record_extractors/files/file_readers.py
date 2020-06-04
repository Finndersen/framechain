import gzip


class BaseFileReader(object):
    """
    Base class for FileReader interface
    Just Callable which takes file object and returns readable file handle
    """

    def __call__(self, file):
        raise NotImplementedError()


class BasicFileReader(BaseFileReader):
    """
    Standard file reader for uncompressed files
    """
    def __init__(self,read_mode='rt',**open_kwargs):
        self.read_mode=read_mode
        self.open_kwargs = open_kwargs

    def __call__(self, file_path):
        return open(file_path, mode=self.read_mode,**self.open_kwargs)


class GzipFileReader(BaseFileReader):
    """
    File reader class for reading GZIP compressed files
    """
    def __init__(self,read_mode='rt',**open_kwargs):
        self.read_mode=read_mode
        self.open_kwargs = open_kwargs

    def __call__(self, file_path):
        return gzip.open(file_path,mode=self.read_mode,**self.open_kwargs)