import csv

import pandas as pd
import numpy as np

from etl_framework.operations.io import TextReader
from etl_framework.operations.pandas.record_extractors.base import InputField, BaseDataFrameGenerator, \
    TimestampFieldMixin, IntegerFieldMixin
from etl_framework.operations.transforms import BytesToString


class DelimitedRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from data file with fields seperated by delimiter character
    Wrapper around pandas.read_csv
    Input is file text or bytes content or file reader object in text mode
    If file contains headers, field header_name attribute is used to match field
    Otherwise, Fields must provide
    """

    def __init__(self, fields, delimiter=',', quoting=csv.QUOTE_MINIMAL, header=True, read_csv_kwargs=None, **kwargs):
        """
        :param tuple/list fields: List/tuple of CSVField(s)
        :param str delimiter: Delimiter character used for CSV reader
        :param quoting: Quoting setting for CSV reader
        :param bool header: Whether field headers are provided in file
        :param dict read_csv_kwargs: Additional arguments to pass to CSV reader
        """
        # Validate fields contain column_id if file has no header
        if not header and not all(isinstance(field.column_id, int) for field in fields):
            self.error(TypeError, 'All field column_ids must be ints if header=False')
        if header and not all(isinstance(field.column_id, str) for field in fields):
            self.error(TypeError, 'All field column_ids must be strings if header=True')

        self.delimiter = delimiter
        self.quoting = quoting
        self.read_csv_kwargs = read_csv_kwargs or {}
        self.header = header
        super().__init__(fields, **kwargs)

    def get_full_dataframe(self, file_data):
        """
        Create dataframe from CSV data file. (Does not support record chunking)
        Input can be file reader object (most efficient), or string or bytes data
        :param file_data:
        :return:
        """
        # Convert input data to text reader object
        if isinstance(file_data, str):
            # Create reader object for string data
            file_data = TextReader()(file_data)
        elif isinstance(file_data, bytes):
            # Convert bytes to text and Create reader object for string data
            file_data = (BytesToString() >> TextReader())(file_data)
        elif not hasattr(file_data, 'read'):
            raise ValueError('Input file data should be str, bytes or reader object, not {}'.format(type(file_data)))

        extract_fields = [field for field in self.fields if field.extract]

        # Get mapping of field header names or column IDs to dtype definitions
        dtypes = {field.column_id: field.dtype
                  for field in extract_fields if field.dtype}
        # Get mapping of field header names or column IDs to converter definitions
        converters = {field.column_id: field.convert_value
                      for field in extract_fields if field.value_converter}

        dataframe = pd.read_csv(file_data,
                                sep=self.delimiter,
                                header=0 if self.header else None,
                                quoting=self.quoting,
                                dtype=dtypes,
                                converters=converters,
                                **self.read_csv_kwargs)

        # Select required columns from dataframe. Do this here instead of using 'usecols' in pd.read_csv() because
        # it disables functionality of error_bad_lines=False or on_bad_lines='skip'
        # If file has headers, use_columns is list of field names (str), otherwise list of field positions (int)
        dataframe = dataframe[[field.column_id for field in extract_fields]]

        # Rename columns to actual field names
        renames = {field.column_id: field.name
                   for field in extract_fields
                   if field.column_id != field.name}
        dataframe.rename(columns=renames, inplace=True)
        # Add record number column
        dataframe[self.RECORDNUMBER_FIELD_NAME] = pd.Series(np.arange(1, len(dataframe.index) + 1))

        return dataframe


class CSVField(InputField):
    """
    Object representing field in delimited (e.g. CSV) file
    """

    def __init__(self, name, column_id=None, **kwargs):
        """

        :param str name: Name of field
        :param int/str column_id: 0-indexed Id of column for this field (for when file does not contain headers)
        or Name of field in file header (for when file contains headers) - defaults to field name
        """
        self.column_id = name if column_id is None else column_id
        super().__init__(name, **kwargs)


class StringField(CSVField):
    """
    Field which converts values to String dtype
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         dtype=object, **kwargs)


class IntegerField(IntegerFieldMixin, CSVField):
    """
    Field which converts values to Nullable Integer type
    """
    pass
    #
    # def __init__(self, name, large=False, **kwargs):
    #     """
    #
    #     :param name:
    #     :param bool large: Whether integer may be very large (greater than 2,147,483,647) (use 64-bit)
    #     :param kwargs:
    #     """
    #     super().__init__(name,
    #                      dtype='Int64' if large else 'Int32',
    #                      **kwargs)


class TimestampField(TimestampFieldMixin, CSVField):
    """
    Field which converts values to Timestamp
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         dtype=object, **kwargs)
