import numpy as np
import pandas as pd

from etl_framework.exceptions import OperationConfigurationError
from etl_framework.operations.io import TextReader
from etl_framework.operations.pandas.record_extractors.base import InputField, \
    BaseDataFrameGenerator, \
    TimestampFieldMixin, IntegerFieldMixin, NumberFieldMixin
from etl_framework.operations.transforms import BytesToString


class DelimitedRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from data file with fields separated by delimiter character. Wrapper for pandas.read_csv()
    Input is file text or bytes content or file reader object in text mode
    If file contains headers, field header_name attribute is used to match field
    Otherwise, Fields must provide
    """

    def __init__(self, fields, delimiter=',', header=True, read_csv_kwargs=None, **kwargs):
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

        defaults = {
            'engine': 'c'  # C engine is faster but not as feature-complete
        }

        if read_csv_kwargs:
            defaults.update(read_csv_kwargs)

        self.delimiter = delimiter
        self.read_csv_kwargs = defaults
        self.header = header
        super().__init__(fields, **kwargs)

    def create_dataframe(self, file_data):
        """
        Create dataframe from CSV data file.
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
        dtypes = {field.column_id: field.read_dtype
                  for field in extract_fields if field.read_dtype}
        # Get mapping of field header names or column IDs to converter definitions
        converters = {field.column_id: field.convert_value
                      for field in extract_fields if field.value_converter}

        # Detect whether bad lines (longer or shorter than expected) should be skipped
        skip_bad_lines = self.read_csv_kwargs.get('on_bad_lines', None) == 'skip'

        dataframe = pd.read_csv(file_data,
                                sep=self.delimiter,
                                header=0 if self.header else None,
                                dtype=dtypes,
                                converters=converters,
                                # usecols breaks bad line skipping so dont use if skip_bad_lines
                                usecols=[field.column_id for field in extract_fields]
                                if not skip_bad_lines else None,
                                **self.read_csv_kwargs)

        if skip_bad_lines:
            # If skipping bad lines, need to select columns here because 'usecols' in read_csv()
            # does not work with on_bad_lines='skip'
            # https://github.com/pandas-dev/pandas/issues/40049
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
    If CSV file does not contain headers, need to specify column_id to map field to column position
    Contains extra configuration for field-specific logic in pd.read_csv()
    - value_converter will be provided as converter function for this field
    - data will be coerced to read_dtype before column conversion (defaults to final field dtype)
    - cannot specify both value_converter and read_type (converter takes precendence)
    """

    def __init__(self, name, column_id=None, dtype=None, read_dtype=None, value_converter=None,
                 **kwargs):
        """

        :param str name: Name of field
        :param int/str column_id: 0-indexed Id of column for this field (for when file does not contain headers)
        or Name of field in file header (for when file contains headers) - defaults to field name
        :param dtype: Desired final dtype of field after column conversion
        :param read_dtype: Dtype to use when reading CSV (before Column Conversion)
        """
        self.column_id = name if column_id is None else column_id
        if value_converter:
            if read_dtype:
                raise OperationConfigurationError(
                    'Do not specify both value_converter and read_dtype for CSVField: "{}"'.format(name))
        elif read_dtype is None:
            # read_dtype defaults to output dtype if not specified
            read_dtype = dtype
        self.read_dtype = read_dtype

        super().__init__(name, dtype=dtype, value_converter=value_converter, **kwargs)


class StringField(CSVField):
    """
    Field which converts values to String dtype
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         dtype=object,
                         **kwargs)


class IntegerField(IntegerFieldMixin, CSVField):
    """
    Field which converts values to Nullable Integer type
    """

    def __init__(self, *args, size=32, **kwargs):
        super().__init__(*args,
                         size=size,
                         read_dtype='Int{}'.format(size),
                         **kwargs)


class NumberField(NumberFieldMixin, CSVField):
    """
    Field which converts values to Numeric type (does not support nullable integer)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         read_dtype=float,
                         **kwargs)


class TimestampField(TimestampFieldMixin, CSVField):
    """
    Field which converts values to Timestamp. Read values as string for parsing
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         read_dtype=object,
                         **kwargs)
