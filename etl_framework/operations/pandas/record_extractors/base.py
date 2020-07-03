from etl_framework.utils import LogDuration
from etl_framework.operations.base import WrappingTypeTranslatorMixin, BaseOperation
from etl_framework.exceptions import ETLConfigurationError
from etl_framework.operations.pandas import ToInteger
import logging

log = logging.getLogger(__name__)


###########################################################################################
# Record extractions take a file handle and yield records in the form of a list of field values
###########################################################################################
class BaseRecordExtractor(BaseOperation):
    """
    Base class for Record Extractor interface
    Must define 'create_dataframe' method which takes some input and produces DataFrame with raw field values
    Requires sequence of BaseField subclasses which correspond to columns in DataFrame and contain conversion logic
    """
    calling_translations = {'input': 'dataframe'}

    def __init__(self, fields):
        """
        :param fields: list/tuple of BaseField subclasses defining fields in file
        """
        # Validate field names are unique
        field_names = set()
        for field in fields:
            if field.name in field_names:
                raise ETLConfigurationError(
                    'Input field: "{}" has already been defined for {}'.format(field.name, type(self).__name__))
            field_names.add(field.name)
        self.fields = fields

    def __call__(self, etl_input):
        """
        Takes ETL input parameter and returns Pandas Dataframe

        :param etl_input: ETL input parameter. Type depends on requirements of specific Record Extractor
        """
        with LogDuration(log, 'Extracting records from input...'):
            dataframe = self.create_dataframe(etl_input)
            #  Add any missing fields as Null column
            for field in self.fields:
                if field.name not in dataframe.columns:
                    dataframe[field.name] = None

        if not dataframe.empty:
            # Perform field vecttor conversions
            with LogDuration(log, 'Performing vector field conversions...'):
                for field in self.fields:
                    dataframe[field.name] = field.convert_column(dataframe[field.name])

        return dataframe

    def create_dataframe(self, etl_input):
        """
        Method used to generate dataframe containing raw field values
        :param etl_input:
        :return: pd.DataFrame
        """
        raise NotImplementedError()


class InputField(WrappingTypeTranslatorMixin):
    """
    Base class for defining a field from a data file, along with relevant conversion logic
    """

    column_converter = None
    value_converter = None
    calling_translations = wrapping_translations = {'dataframe': 'column'}

    def __init__(self, name, column_converter=None, value_converter=None):
        """

        :param str name: Name of field
        :param callable column_converter: Custom converter function which takes column of raw field values, and returns column of converted values
        :param callable value_converter: Custom function which converts takes raw field value before Dataframe is constructed
        """
        self.name = name.lower()
        self.column_converter = column_converter or self.column_converter
        self.value_converter = value_converter or self.value_converter
        # Validate converter type compatability
        if self.column_converter:
            self.validate_wrapped_operation_compatability(self.column_converter)

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
        Perform single value conversion
        :param value:
        :return:
        """
        if self.value_converter:
            return self.value_converter(value)
        else:
            return value

    def __str__(self):
        return '{}: "{}"'.format(type(self).__name__, self.name)


class IntegerFieldMixin(object):
    """
    Mixin for integer type fields
    Adds ToInteger() converter to ensure field stays as integer type even if it contains null values
    """

    def __init__(self, *args, int_size=32, force_int=True, column_converter=None, **kwargs):
        """

        :param int int_size: Integer size in bits
        :param bool force_int: Whether to apply ToInteger() converter
        """
        if force_int:
            converter = ToInteger(int_size) >> column_converter if column_converter else ToInteger(int_size)
        else:
            converter = column_converter

        super().__init__(*args,
                         column_converter=converter,
                         **kwargs)
