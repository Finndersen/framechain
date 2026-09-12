import logging

import numpy as np
import pandas as pd

from etl_framework.exceptions import OperationConfigurationError, MandatoryFieldError
from etl_framework.operations import BaseOperation, Operation, profiled, Pass
from etl_framework.operations.pandas.transforms import ToNullableInteger, SetColumnTimezone, ColumnToDatetime, AsType, \
    ToNumeric
from etl_framework.operations.pandas.utils import concat_dataframes
from etl_framework.utils import LogDuration, chunks

log = logging.getLogger(__name__)


###########################################################################################
# Record extractions take a file handle and yield records in the form of a list of field values
###########################################################################################
class BaseDataFrameGenerator(Operation):
    """
    Base class for operation which extracts records from some input to generate a DataFrame
    Must define 'create_dataframe' method which takes some input and produces DataFrame with raw field values
    Requires sequence of BaseField subclasses which correspond to columns in DataFrame and contain conversion logic
    """

    def __init__(self, fields, record_number_field_name='_record_number'):
        """
        :param list/tuple of InputFields fields: List of Field instances to define extraction and conversion logic
        :param str, None record_number_field_name: Name of field to store record number in. Should represent original record
        number in source, not necessarily record number in output DF
        """
        super().__init__()

        self.RECORDNUMBER_FIELD_NAME = record_number_field_name
        if record_number_field_name:
            # Add field for Record Number (which only does post-processing and not extraction)
            fields = list(fields) + [NonExtractedField(record_number_field_name,
                                                       column_converter=ToNumeric(downcast='unsigned'))]

        self.fields = [self.add_child_operation(field) for field in fields]

        # Validate field names are unique
        field_names = set()
        for field in self.fields:
            if not isinstance(field, InputField):
                raise TypeError('Fields should be subclasses of InputField')

            if field.name in field_names:
                raise OperationConfigurationError(
                    'Input field: "{}" has already been defined for {}'.format(field.name, type(self).__name__))
            field_names.add(field.name)

    def action(self, input_data):
        """
        Construct dataframe from input and perform field post-processing

        :param input_data: ETL input data. Type depends on requirements of specific Record Extractor
        """
        with LogDuration(log,
                         'Extracting records from input...'):  # TODO: Remove logging and add dedicated operation for logging
            dataframe = self.create_dataframe(input_data)

        # Perform field vectorised conversions
        dataframe = self.post_process_dataframe(dataframe)

        # Order fields
        dataframe = self.order_fields(dataframe)

        return dataframe

    def create_dataframe(self, input_data):
        """
        Build full dataframe of records
        :param input_data:
        :return: pd.DataFrame
        """
        raise NotImplementedError()

    def post_process_dataframe(self, dataframe):
        """
        Perform field column conversions and add any missing fields
        :param dataframe:
        :return:
        """
        with LogDuration(log, 'Performing vector field conversions...'):
            for field in self.fields:
                if field.post_process:
                    #  Add any missing fields as Null column
                    if field.name not in dataframe.columns:
                        dataframe[field.name] = pd.Series(np.nan, dtype=object)
                    # Perform column processing (check for mandatory, set dtypes, custom conversions)
                    dataframe[field.name] = field.convert_column(dataframe[field.name])

        return dataframe

    def order_fields(self, dataframe):
        """
        Set dataframe column order
        :param dataframe:
        :return:
        """
        return dataframe[[field.name for field in self.fields if field.post_process]]


class IterableRecordsDataframeGenerator(BaseDataFrameGenerator):
    """
    Dataframe generator which is able to extract records from source in a streamed fashion (record by record, not all
    at once)
    Allows option of applying record processor to each record and building dataframe in chunks for memory optimisation
    Any new field added by record processor should have a corresponding NonExtractedField definition
    Any field removed by record processor should have post_process=False
    """

    def __init__(self, fields, record_processor=None, record_type_field_name='_record_type', chunk_size=None, **kwargs):
        """

        :param list, tuple fields:
        :param record_processor: Optional callable used to process each record before being provided to DataFrame initialisation
        :param str, None record_type_field_name: Name to give record type of each record
        :param int chunk_size: Length of record chunks to construct dataframe from (can save memory usage)
        :param kwargs:
        """
        # Add field for Record Type (which only does post-processing and not extraction)
        if record_type_field_name:
            fields = list(fields) + [NonExtractedField(record_type_field_name, column_converter=AsType('category'))]

        super().__init__(fields, **kwargs)
        self.chunk_size = chunk_size
        self.RECORDTYPE_FIELD_NAME = record_type_field_name
        self.record_processor = self.add_child_operation(record_processor, none_allowed=True)

    def action(self, input_data):
        """
        Build full dataframe of records, by concatenating sub-dataframes of chunks of records
        :param input_data:
        :return: pd.DataFrame
        """
        # Get iterable of record chunks
        if self.record_processor:
            records = (self.record_processor(record)
                       for record in self.get_records(input_data))
        else:
            records = self.get_records(input_data)

        # Build list of sub-dataframes and Join together into one dataframe
        dataframes = [self.post_process_dataframe(self.create_dataframe(records_chunk))
                      for records_chunk in chunks(records, self.chunk_size)]

        if dataframes:
            dataframe = concat_dataframes(dataframes)
        else:
            # No records, make empty dataframe
            dataframe = self.create_dataframe([])

        # Order fields
        dataframe = self.order_fields(dataframe)

        return dataframe

    def get_records(self, input_data):
        """
        Return sequence of records from input data (can be dicts, tuples, lists, etc)
        Should ideally yield records to act as an generator for memory efficiency
        :param input_data:
        :return:
        """
        raise NotImplementedError()

    def create_dataframe(self, records):
        """
        Construct a dataframe from a chunk of records
        Faster to construct when specifying columns
        :param records:
        :return:
        """
        return pd.DataFrame(records,
                            columns=[field.name for field in self.fields if field.post_process])


class InputField(BaseOperation):
    """
    Class for defining a field in a source data record which will correspond to a DataFrame column
    Contains logic for:
    - Extraction and conversion of raw field value from source e.g. File
    - Data type conversion and missing value check on Dataframe Column (series) for this field
    """

    # Values which will be treated as Null
    EMPTY_VALUES = {''}
    extract = True

    def __init__(self, name, mandatory=False, column_converter=None, value_converter=None,
                 ignore_condition=None, dtype=None, categorical=False, post_process=True):
        """

        :param str name: Name of field
        :param bool mandatory: Whether field is mandatory
        :param callable column_converter: Callable which takes column of raw field values,
        and returns column of converted values
        :param callable value_converter: Callable which converts raw field value before Dataframe is constructed
        :param callable ignore_condition: Callable which takes raw value and if returns True, result will be None and
        value conversion is skipped
        :param dtype: Data type to cast column to. Useful for if column has no values to set type appropriately
        :param bool categorical: Whether field column should be converted to Category type (for memory efficiency)
        :param bool post_process: Whether to perform the column post-processing operations for this field
        operations for this field
        """
        super().__init__()
        self.name = name
        self.mandatory = mandatory
        self.column_converter = self.add_child_operation(
            Pass() >>
            (AsType(dtype, copy=False) if dtype else None) >>
            column_converter >>
            (AsType('category', copy=False) if categorical else None)
            # TODO: Change to Ordered Categorical type when pandas upgraded
        )
        self.value_converter = self.add_child_operation(value_converter, none_allowed=True)
        self.ignore_condition = self.add_child_operation(ignore_condition, none_allowed=True)
        self.dtype = dtype
        self.categorical = categorical
        self.post_process = post_process

    def action(self, value):
        """
        Perform conversion of raw field value
        :param value: raw field value
        :return:
        """
        if value in self.EMPTY_VALUES:
            return None

        if self.ignore_condition and self.ignore_condition(value):
            return None

        # Convert value if present
        if value is not None and self.value_converter:
            value = self.value_converter(value)

        return value

    @profiled
    def convert_column(self, column):
        """
        perform vectorised value conversion for field
        :param column: Pandas series containing raw field values
        :return:
        """
        # Check if any values are missing for mandatory field
        if self.mandatory and column.isnull().values.any():
            raise MandatoryFieldError('Mandatory field: {} has missing values'.format(self))

        # Perform vectorised value conversion
        if self.column_converter:
            column = self.column_converter(column)

        return column

    def convert_value(self, value):
        """
        Perform conversion and validation of raw field value
        :param value: raw field value
        :return:
        """
        return self(value)

    def description(self):
        return '{}: "{}"'.format(type(self).__name__, self.name)


class NonExtractedField(InputField):
    """
    Special field class to represent field which is not extracted from source data but generated/added some other way
    e.g. by Dataframe generator or record processor. Has no value conversion logic
    """
    extract = False

    def __init__(self, name, **kwargs):
        if 'value_converted' in kwargs:
            raise ValueError('Cannot provide value converter to {}'.format(type(self).__name__))
        super().__init__(name, **kwargs)


class IntegerFieldMixin(object):
    """
    Mixin for nullable integer type fields
    Adds column converter to convert to nullable integer type if field is float type (due to null values)
    Value converter should return values as numeric (int/float or None)
    """

    def __init__(self, *args, size=32, **kwargs):
        """

        :param int size: Whether to use large integer (64 bits instead of 32)
        """
        super().__init__(*args, column_converter=ToNullableInteger(size=size), **kwargs)


class NumberFieldMixin(object):
    """
    Mixin for number fields (either decimal or integer, but does not support nullable integer)
    """
    def __init__(self, *args, downcast='integer', **kwargs):
        """
        :param str downcast:
        """
        super().__init__(*args, column_converter=ToNumeric(downcast=downcast), **kwargs)


class TimestampFieldMixin(object):
    """
    Mixin for Timestamp fields with optional timezone
    """

    def __init__(self, *args, time_format=None, timezone=None, **kwargs):
        """

        :param str time_format: Timestamp format string. Can be left as None to attempt to infer standard formats
        :param str timezone: Timezone to apply to entire timestamp column (if timestamp does not contain timezone info)
        """
        column_converter = ColumnToDatetime(time_format)
        if timezone:
            column_converter = column_converter >> SetColumnTimezone(timezone)

        super().__init__(*args,
                         column_converter=column_converter,
                         **kwargs)
