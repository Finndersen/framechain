
from etl_framework.operations.pandas.output_generators.base import BaseDataframeExporter
import logging, io

log = logging.getLogger(__name__)


class DataFrameToCSVExporter(BaseDataframeExporter):
    """
    Basic CSV output generator to generate CSV file content as text string
    Can then use LocalFileWriter to write result to file
    """

    calling_translations = {'dataframe': 'file_data'}

    def __init__(self, columns=None, delimiter=',', line_terminator='\n', create_for_empty=False, **to_csv_kwargs):
        """
        :param sequence columns: sequence of field names to write. Will use all if not specified
        :param str delimiter: field delimiter character
        :param str line_terminator: line terminator string
        :param bool create_for_empty: Whether to create output file when dataframe is empty
        :param to_csv_kwargs: extra arguments to provide to pandas.to_csv()
        """
        self.delimiter = delimiter
        self.line_terminator = line_terminator
        self.writer_kwargs = to_csv_kwargs
        super().__init__(columns=columns, create_for_empty=create_for_empty)

    def generate_output(self, dataframe):
        buffer = io.StringIO()
        # Generate file
        dataframe.to_csv(buffer,
                         sep=self.delimiter,
                         columns=self.columns,
                         index=False,
                         line_terminator=self.line_terminator,
                         **self.writer_kwargs)
        return buffer.getvalue()

    def description(self):
        return 'Convert Dataframe to CSV data'
