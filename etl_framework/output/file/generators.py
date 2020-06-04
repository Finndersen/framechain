from etl_framework.exceptions import MissingFieldError
from etl_framework.output.base import BaseOutputGenerator
import logging

log = logging.getLogger(__name__)


class BaseFileOutputGenerator(BaseOutputGenerator):
    """
    Base class for any kind of output generator that writes to file
    The generator handles the file format (content of the file)
    Requires a writer class (Callable which returns file writer, and has get_return_value() method)
    The writer handles filename and destination (local filesystem, network storage, HDFS, etc)
    """

    def __init__(self, writer, columns=None, **kwargs):
        """
        :param writer: Subclass of OutputWriter (Callable which returns file writer, and has get_return_value() method)
        :param sequence columns: sequence of field names to write
        """
        self.writer = writer
        self.columns = columns
        super().__init__(**kwargs)

    def generate_output(self, dataframe):
        # Verify all desired output columns are in dataframe
        if self.columns:
            for column in self.columns:
                if column not in dataframe.columns:
                    raise MissingFieldError('Dataframe is missing expected output column: "{}"'.format(column))
        log.debug("Generating file at: {}".format(self.writer))
        with self.writer() as writer:
            self.write_to_file(writer, dataframe)

    def write_to_file(self, writer, dataframe):
        """
        Write dataframe content to output writer
        :param writer:
        :param dataframe:
        :return:
        """
        raise NotImplementedError()

    def get_return_value(self, generate_result):
        return self.writer.get_return_value()


class CSVOutputGenerator(BaseFileOutputGenerator):
    """
    Basic CSV output generator to create CSV file content
    """

    def __init__(self, writer, columns=None, delimiter=',', header=True, line_terminator='\n', float_format=None,
                 writer_kwargs=None, **kwargs):
        """
        :param writer: Callable which returns file writer to write to (e.g. local filesystem, HDFS)
        :param sequence columns: sequence of field names to write. Will use all if not specified
        :param str delimiter: field delimiter character
        :param bool or list of str header: Whether to write field names, or aliases for field names
        :param str line_terminator: line terminator string
        :param str float_format: Optional formatting string for float values
        :param dict writer_kwargs: extra arguments to provide to pandas.to_csv()
        """
        self.header = header
        self.delimiter = delimiter
        self.line_terminator = line_terminator
        self.float_format = float_format
        self.writer_kwargs = writer_kwargs or {}
        super().__init__(writer, columns, **kwargs)

    def write_to_file(self, writer, dataframe):
        # Generate file
        dataframe.to_csv(writer,
                         sep=self.delimiter,
                         columns=self.columns,
                         header=self.header,
                         index=False,
                         line_terminator=self.line_terminator,
                         float_format=self.float_format,
                         **self.writer_kwargs)

    def __str__(self):
        return 'Write to CSV at: {}'.format(self.writer)


class ParquetFileOutputGenerator(BaseFileOutputGenerator):
    """
    Output file generator to produce Parquet file type
    Make it quite generic to include any desired configuration parameters in __init__()
    Do not include reference to anything Darwin-specific
    TODO: (Naveed)
    """

    def __init__(self, writer, columns=None, ):
        """
        #TODO: Add extra Parquet-specific configuration parametrs
        :param writer:
        :param columns:
        """

        super().__init__(writer, columns=columns)

    def write_to_file(self, writer, dataframe):
        """
        Write file to output in Parquet format
        :param writer:
        :param dataframe:
        :return:
        """
        raise NotImplementedError()