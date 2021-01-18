
from etl_framework.operations.pandas.output_generators.base import BaseDataframeExporter
import logging, io

log = logging.getLogger(__name__)


class DataFrameToCSVExporter(BaseDataframeExporter):
    """
    Basic CSV output generator to generate CSV file content as text string
    Can then use LocalFileWriter to write result to file
    """

    calling_translations = {'dataframe': 'file_data'}

    def __init__(self, columns=None, delimiter=',', header=True, line_terminator='\n', float_format=None,
                 writer_kwargs=None, **kwargs):
        """
        :param sequence columns: sequence of field names to write. Will use all if not specified
        :param str delimiter: field delimiter character
        :param bool/list of str header: Whether to write field names, or aliases for field names
        :param str line_terminator: line terminator string
        :param str float_format: Optional formatting string for float values
        :param dict writer_kwargs: extra arguments to provide to pandas.to_csv()
        """
        self.header = header
        self.delimiter = delimiter
        self.line_terminator = line_terminator
        self.float_format = float_format
        self.writer_kwargs = writer_kwargs or {}
        super().__init__(columns=columns, **kwargs)

    def generate_output(self, dataframe):
        buffer = io.StringIO()
        # Generate file
        dataframe.to_csv(buffer,
                         sep=self.delimiter,
                         columns=self.columns,
                         header=self.header,
                         index=False,
                         line_terminator=self.line_terminator,
                         float_format=self.float_format,
                         **self.writer_kwargs)
        return buffer.getvalue()

    def description(self):
        return 'Convert Dataframe to CSV data'
