import logging

from framechain.operations.pandas.output_generators.base import BaseDataframeExporter

log = logging.getLogger(__name__)


class DataFrameToCSVExporter(BaseDataframeExporter):
    """
    Basic CSV output generator to generate CSV file content as text string
    Can then use LocalFileWriter to write result to file
    """

    def __init__(self, output=None, columns=None, delimiter=',', lineterminator='\n', create_for_empty=False,
                 **to_csv_kwargs):
        """
        :param str, file handle, None output: File path or object to write content to,
        or if None is provided the result is returned as a string
        :param sequence columns: sequence of field names to write. Will use all if not specified
        :param str delimiter: field delimiter character
        :param str lineterminator: line terminator string
        :param bool create_for_empty: Whether to create output file when dataframe is empty
        :param to_csv_kwargs: extra arguments to provide to pandas.to_csv()
        """
        self.output = output
        self.delimiter = delimiter
        self.lineterminator = lineterminator
        self.writer_kwargs = to_csv_kwargs
        super().__init__(columns=columns, create_for_empty=create_for_empty)

    def generate_output(self, dataframe):

        # Generate file
        return dataframe.to_csv(self.output,
                                sep=self.delimiter,
                                columns=self.columns,
                                index=False,
                                lineterminator=self.lineterminator,
                                **self.writer_kwargs)

    def description(self):
        if self.output:
            return 'Write dataframe to CSV at: {}'.format(self.output if isinstance(self.output, str)
                                                          else self.output.name)
        else:
            return 'Convert Dataframe to CSV string data'
