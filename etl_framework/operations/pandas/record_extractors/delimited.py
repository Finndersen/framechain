import csv, io
from darwin.core import darwin_logging
import pandas as pd
from etl_framework.exceptions import ETLConfigurationError
from etl_framework.operations.pandas.record_extractors.base import InputField, BaseRecordExtractor
from etl_framework.operations.transforms import StringToDatetime

log = darwin_logging.get_logger(__name__)


class DelimitedRecordExtractor(BaseRecordExtractor):
    """
    Extract records from data file with fields seperated by delimiter character
    Wrapper around pandas.read_csv
    Input is file reader object in text mode
    If file contains headers, field header_name attribute is used to match field
    Otherwise, Fields must provide
    """

    def __init__(self, fields, delimiter=',', quoting=csv.QUOTE_MINIMAL, header=True, **read_csv_kwargs):
        """
        :param tuple fields: List/tuple of CSVField(s)
        :param str delimiter: Delimeter character used for CSV reader
        :param quoting: Quoting setting for CSV reader
        :param bool header: Whether field headers are provided in file
        :param dict read_csv_kwargs: Additional arguments to pass to CSV reader
        """
        # Validate fields contain column_id if file has no header
        if not header and not all(isinstance(field.column_id, int) for field in fields):
            raise ETLConfigurationError('All field column_ids must be ints if header=False')
        if header and not all(isinstance(field.column_id, str) for field in fields):
            raise ETLConfigurationError('All field column_ids must be strings if header=True')

        self.delimiter = delimiter
        self.quoting = quoting
        self.read_csv_kwargs = read_csv_kwargs
        self.header = header
        super().__init__(fields)

    def create_dataframe(self, file_reader):
        # If file has headers, use_columns is list of field names, otherwise list of field positions
        use_columns = [field.column_id for field in self.fields]
        # Get mapping of field header names or column IDs to dtype definitions
        dtypes = {field.column_id: field.dtype
                  for field in self.fields if field.dtype}
        # Get mapping of field header names or column IDs to converter definitions
        converters = {field.column_id: field.value_converter
                      for field in self.fields if field.value_converter}

        dataframe = pd.read_csv(file_reader,
                                sep=self.delimiter,
                                header=0 if self.header else None,
                                quoting=self.quoting,
                                usecols=use_columns,
                                dtype=dtypes,
                                converters=converters,
                                **self.read_csv_kwargs)

        # Rename columns to actual field names
        renames = {field.column_id: field.name
                   for field in self.fields
                   if field.column_id != field.name}
        dataframe.rename(columns=renames, inplace=True)

        return dataframe


class CSVField(InputField):
    """
    Object used to define details of a CSV field
    """

    def __init__(self, name, column_id=None, dtype=None, **kwargs):
        """

        :param str name: Name of field
        :param int/str column_id: 0-indexed Id of column for this field (for when file does not contain headers)
        or Name of field in file header (for when file contains headers) - defaults to field name
        :param str dtype: Data type to convert to (e.g. 'float64', 'int64', 'int32')
        """
        self.column_id = name if column_id is None else column_id
        self.dtype = dtype
        super().__init__(name, **kwargs)


class TimestampField(CSVField):
    def __init__(self, name, format, **kwargs):
        converter = StringToDatetime(format)
        super().__init__(name, value_converter=converter, **kwargs)
