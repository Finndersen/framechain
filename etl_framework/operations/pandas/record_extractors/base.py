from etl_framework.utils import LogDuration
from etl_framework.operations.base import BaseOperation, OperatorWrapperMixin, CompoundOperation
from etl_framework.exceptions import ETLConfigurationError, MandatoryFieldError
from etl_framework.operations.transforms import StringToDatetime
from etl_framework.operations.pandas.transforms import ToInteger, SetColumnTimezone, StringColumnToDatetime
import logging
from time import perf_counter

log = logging.getLogger(__name__)


###########################################################################################
# Record extractions take a file handle and yield records in the form of a list of field values
###########################################################################################
class BaseDataFrameGenerator(CompoundOperation):
    """
    Base class for operation which extracts records from some input to generate a DataFrame
    Must define 'create_dataframe' method which takes some input and produces DataFrame with raw field values
    Requires sequence of BaseField subclasses which correspond to columns in DataFrame and contain conversion logic
    """

    def __init__(self, fields):
        """
        :param fields: list/tuple of InputField subclasses defining fields to be extracted from input
        and turned into DataFrame columns
        """
        # Validate field names are unique
        field_names = set()
        for field in fields:
            if not isinstance(field, InputField):
                raise TypeError('Fields should be subclasses of InputField')

            if field.name in field_names:
                raise ETLConfigurationError(
                    'Input field: "{}" has already been defined for {}'.format(field.name, type(self).__name__))
            field_names.add(field.name)
        self.fields = fields
        super().__init__(*self.fields)

    def action(self, input_data):
        """
        Takes ETL input parameter and returns Pandas Dataframe

        :param input_data: ETL input data. Type depends on requirements of specific Record Extractor
        """
        with LogDuration(log, 'Extracting records from input...'):  # TODO: Remove logging and add dedicated operation for logging
            dataframe = self.create_dataframe(input_data)
            #  Add any missing fields as Null column
            for field in self.fields:
                if field.name not in dataframe.columns:
                    dataframe[field.name] = None

        if not dataframe.empty:
            # Perform field vector conversions
            with LogDuration(log, 'Performing vector field conversions...'):
                for field in self.fields:
                    dataframe[field.name] = self.run_wrapped_operation(field, dataframe[field.name])

        # Order columns as input field order
        if self.fields:
            dataframe = dataframe[[field.name for field in self.fields]]

        return dataframe

    def create_dataframe(self, input_data):
        """
        Method used to generate dataframe containing raw field values
        :param input_data:
        :return: pd.DataFrame
        """
        raise NotImplementedError()

    def get_execute_time(self):
        """
        Get of just this operation (not including any wrapped sub-operations)
        Subtract both Field value convert and column convert times
        Assumes Field instances are not re-used elsewhere...
        :return:
        """
        exec_time = self.get_cumulative_time()
        for field in self.fields:
            exec_time -= field.get_cumulative_time()
        return exec_time

    def get_wrapped_operation_stats(self, wrapped_operation):
        """
        BaseDataFrameGenerator does not have visibility of Field.convert_value execution time
        Assume this is the only caller of the field instance and return full field stats
        :param wrapped_operation:
        :return:
        """
        return wrapped_operation.get_execution_stats()


class InputField(OperatorWrapperMixin, BaseOperation):
    """
    Class for defining a field in a source data record which will correspond to a DataFrame column
    Performs vectorised value conversion on field column when called
    Is a compound operation because associated converters are operations
    """
    column_converter = None
    value_converter = None
    EMPTY_VALUES = {''}   # Values which will be converted to None

    def __init__(self, name, mandatory=False, column_converter=None, value_converter=None):
        """

        :param str name: Name of field
        :param bool mandatory: Whether field is mandatory
        :param callable column_converter: Custom converter function which takes column of raw field values, and returns column of converted values
        :param callable value_converter: Custom function which converts takes raw field value before Dataframe is constructed
        """
        self.name = name
        self.mandatory = mandatory
        self.column_converter = column_converter or self.column_converter
        self.value_converter = value_converter or self.value_converter
        super().__init__(*[converter for converter in [self.column_converter, self.value_converter]
                          if converter is not None])

    def action(self, column):
        """
        perform vectorised value conversion for field
        :param column: Pandas series containing raw field values
        :return:
        """
        # Perform vectorised value conversion
        if self.column_converter:
            column = self.run_wrapped_operation(self.column_converter, column)

        return column

    def convert_column(self, column):
        """
        perform vectorised value conversion for field
        :param column: Pandas series containing raw field values
        :return:
        """
        self(column)

    def convert_value(self, value):
        """
        Perform conversion and validation of raw field value
        :param value:
        :return:
        """
        if self.profiling_enabled:
            start_time = perf_counter()

        if value in self.EMPTY_VALUES:
            value = None

        if value is None:
            if self.mandatory:
                raise MandatoryFieldError('Mandatory field: {} has empty value'.format(self))
        else:
            self.validate_raw_value(value)
            if self.value_converter:
                value = self.run_wrapped_operation(self.value_converter, value)

        if self.profiling_enabled:
            self._cumulative_time += perf_counter() - start_time
            self.call_count += 1
        return value

    def validate_raw_value(self, value):
        """
        Validate non-null raw field value (before value conversion)
        :param value:
        :return:
        """
        pass

    def description(self):
        return '{}: "{}"'.format(type(self).__name__, self.name)


class IntegerFieldMixin(object):
    """
    Mixin for integer type fields
    Adds column converter to convert to nullable integer type if field is float type (due to null values)
    """

    def __init__(self, *args, large=False, **kwargs):
        """

        :param bool large: Whether to use large integer (64 bits instead of 32)
        """
        if 'column_converter' in kwargs:
            column_converter = ToInteger(large) >> kwargs.pop('column_converter')
        else:
            column_converter = ToInteger(large)
        super().__init__(*args, column_converter=column_converter, **kwargs)


class TimestampFieldMixin(object):
    """
    Mixin for Timestamp fields with optional timezone
    """
    def __init__(self, *args, time_format=None, timezone=None, **kwargs):
        """

        :param str time_format: Timestamp format string. Can be left as None to attempt to infer standard formats
        :param str timezone: Timezone to apply to entire timestamp column (if timestamp does not contain timezone info)
        """
        column_converter = StringColumnToDatetime(time_format)
        if timezone:
            column_converter = column_converter >> SetColumnTimezone(timezone)

        super().__init__(*args,
                         column_converter=column_converter,
                         # value_converter=StringToDatetime(time_format),
                         **kwargs)
