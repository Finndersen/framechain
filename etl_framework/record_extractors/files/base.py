from etl_framework.record_extractors.base import BaseRecordExtractor


class FileRecordExtractor(BaseRecordExtractor):
    """
    Record Extractor for extracting records from a source file
    Input is path to source file
    Requires file reader callable which takes file path and returns file-like object for reading
    Subclasses need to override dataframe_from_file()
    """
    def __init__(self, file_reader, fields):
        """

        :param file_reader: callable which takes file path and returns file-like object for reading
        :param fields: sequence of BaseField subclasses
        """
        self.file_reader = file_reader
        super().__init__(fields)

    def build_raw_dataframe(self, file_path):
        """

        :param str file_path: path to source file
        :return:
        """
        # Open file and build dataframe
        with self.file_reader(file_path) as input_file:
            return self.dataframe_from_file(input_file)

    def dataframe_from_file(self, input_file):
        """
        Extract records from file to build dataframe
        :param input_file: file object open for reading
        :return:
        """
        raise NotImplementedError()

    def __str__(self):
        return 'Extract fields: [{}] from file'.format(', '.join(str(field) for field in self.fields))