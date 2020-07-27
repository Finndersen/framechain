from etl_framework.utils import LogDuration
from etl_framework.operations.base import WrappingTypeTranslatorMixin, BaseOperation
from etl_framework.exceptions import ETLConfigurationError, MandatoryFieldError
from etl_framework.operations.transforms import StringToDatetime
from etl_framework.operations.pandas.transforms import ToInteger, SetColumnTimezone, StringColumnToDatetime
import logging

log = logging.getLogger(__name__)


###########################################################################################
# Record extractions take a file handle and yield records in the form of a list of field values
###########################################################################################
class BaseDataFrameGenerator(BaseOperation):
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
            if field.name in field_names:
                raise ETLConfigurationError(
                    'Input field: "{}" has already been defined for {}'.format(field.name, type(self).__name__))
            field_names.add(field.name)
        self.fields = fields

    def __call__(self, input_data):
        """
        Takes ETL input parameter and returns Pandas Dataframe

        :param input_data: ETL input data. Type depends on requirements of specific Record Extractor
        """
        with LogDuration(log, 'Extracting records from input...'):
            dataframe = self.create_dataframe(input_data)
            #  Add any missing fields as Null column
            for field in self.fields:
                if field.name not in dataframe.columns:
                    dataframe[field.name] = None

        if not dataframe.empty:
            # Perform field vector conversions
            with LogDuration(log, 'Performing vector field conversions...'):
                for field in self.fields:
                    dataframe[field.name] = field.convert_column(dataframe[field.name])

        # Order columns as input field order
        dataframe = dataframe[[field.name for field in self.fields]]

        return dataframe

    def create_dataframe(self, input_data):
        """
        Method used to generate dataframe containing raw field values
        :param input_data:
        :return: pd.DataFrame
        """
        raise NotImplementedError()


class InputField(object):
    """
    Class for defining a field in a source data record which will correspond to a DataFrame column
    """

    column_converter = None
    value_converter = None
    calling_translations = wrapping_translations = {'dataframe': 'column'}
    EMPTY_VALUES = {''}   # Values which will be converted to None

    def __init__(self, name, mandatory=False, column_converter=None, value_converter=None):
        """

        :param str name: Name of field
        :param bool mandatory: Whether field is mandatory
        :param callable column_converter: Custom converter function which takes column of raw field values, and returns column of converted values
        :param callable value_converter: Custom function which converts takes raw field value before Dataframe is constructed
        """
        self.name = name.lower()
        self.mandatory = mandatory
        self.column_converter = column_converter or self.column_converter
        self.value_converter = value_converter or self.value_converter
        # Validate converter type compatibility
        # if self.column_converter:
        #     self.validate_wrapped_operation_compatibility(self.column_converter)

    def convert_column(self, column):
        """
        perform vectorised value conversion for field
        :param column: Pandas series containing raw field values
        :return:
        """
        # Perform vectorised value conversion
        if self.column_converter:
            with LogDuration(log, 'Conversion for {}: {}'.format(self.name, self.column_converter)):
                return self.column_converter(column)
        else:
            return column

    def convert_value(self, value):
        """
        Perform conversion and validation of raw field value
        :param value:
        :return:
        """
        if value in self.EMPTY_VALUES:
            value = None

        if value is None:
            if self.mandatory:
                raise MandatoryFieldError('Mandatory field: {} has empty value'.format(self))
            else:
                return None

        self.validate_raw_value(value)

        if self.value_converter:
            return self.value_converter(value)
        else:
            return value

    def validate_raw_value(self, value):
        """
        Validate non-null raw field value (before value conversion)
        :param value:
        :return:
        """
        pass

    def __str__(self):
        return '{}: "{}"'.format(type(self).__name__, self.name)


class IntegerFieldMixin(object):
    """
    Mixin for integer type fields
    Adds column converter to convert to nullable integer type if field is float type (due to null values)
    """

    def __init__(self, *args, int_size=32, **kwargs):
        """

        :param int int_size: Integer size in bits
        """
        super().__init__(*args, column_converter=ToInteger(int_size), **kwargs)


class TimestampFieldMixin(object):
    """
    Mixin for Timestamp fields with optional timezone
    """
    def __init__(self, *args, time_format=None, timezone=None, **kwargs):
        """

        :param str time_format: Timestamp format string, or None to auto detect if in ISO format
        :param str timezone: Timezone to apply to timestamp
        """
        super().__init__(*args,
                         column_converter=SetColumnTimezone(timezone) if timezone else None,
                         value_converter=StringToDatetime(format=time_format), **kwargs)
