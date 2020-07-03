from etl_framework.operations.base import BaseOperation, TypeTranslations
from etl_framework.operations.general import Map
from etl_framework.exceptions import ETLConfigurationError
import pandas as pd

from etl_framework.operations.pandas.base import ColumnOperation
from etl_framework.operations.wrappers import OperationWrapper


class Field(BaseOperation):
    """
    Operation used to select a column of a Dataframe or a field value of a Row
    """
    calling_translations = {
        'dataframe': 'column',
        'row': 'value'
    }

    def __init__(self, field_name):
        """

        :param field_name: Name of column to select
        """
        if not isinstance(field_name, str):
            raise ETLConfigurationError('Field name must be string')
        self.field_name = field_name

    def __call__(self, multiple_fields):
        """
        :param multiple_fields: Dataframe or Row containing multiple fields
        return:
        """
        # Make copy of column to avoid SettingWithCopyWarning
        if isinstance(multiple_fields, pd.DataFrame):
            return multiple_fields[self.field_name]#.copy()
        else:
            return multiple_fields[self.field_name]

    def __str__(self):
        return 'Field: "{}"'.format(self.field_name)


class ColumnMap(Map, ColumnOperation):
    """
    Provide mapping dictionary which will be used to Convert column values
    Can specify logic for what happens when lookup values are missing (raise error, pass through key, use default)
    """
    ORIGINAL = object()
    ERROR = object()

    calling_translations = {
        'column': 'column'
    }

    def __call__(self, value):
        """Apply mapping to column or value"""
        return value.map(self.mapping)


class Apply(OperationWrapper):
    """
    Wrapper which translates input from vector to scalar in Column axis
    e.g. Dataframe - > rows or Series -> values
    Also supports optional caching of transform output
    """
    wrapping_translations = {
        'dataframe': 'row',
        'column': 'value'
    }

    calling_translations = {
        'dataframe': 'column',
        'column': 'column'
    }

    def __call__(self, vector):
        """
        :param vector: Dataframe or Column (series)
        :return:
        """
        if isinstance(vector, pd.DataFrame):
            return vector.apply(lambda row: self.operation(row), axis=1)
        elif isinstance(vector, pd.Series):
            return vector.apply(lambda value: self.operation(value))
        else:
            self.error(ValueError, 'Input should be DataFrame or Series')

    def __str__(self):
        return 'Apply ({}) to each row'.format(self.operation)


class ColumnMask(OperationWrapper):
    """
    Masking wrapper which takes column, applies conditional logic to produce mask,
    and passes masked column to wrapped operation, and then integrate output values into returned series
    Full Dataframe mask wrapper would require knowledge of output column name, so then it effectively becomes a Transform Constructor
    """
    condition_input_type = 'column'
    wrapping_translations = calling_translations = {'column': 'column'}

    def __init__(self, condition, operation):
        """

        :param condition: Callable which takes column and returns boolean series mask
        :param operation: Operation to pass masked column to
        """
        # Validate type compatability of condition
        if self.condition_input_type not in TypeTranslations.get_for_operation(condition):
            self.error(ETLConfigurationError, 'Condition: {} is not compatible'.format(condition))
        self.condition = condition
        super().__init__(operation)

    def __call__(self, input_column):
        # Get mask using condition
        mask = self.condition(input_column)
        # Provide masked column to operation
        transformed_values = self.operation(input_column.loc[mask])
        # Make copy of column to avoid SettingWithCopyWarning
        output_column = input_column.copy()
        # Integrate values back into original column
        output_column.loc[mask] = transformed_values
        return output_column

    def __str__(self):
        return 'Select values which match condition ({}) and provide to ({})'.format(self.condition, self.operation)


class ColumnOfValue(BaseOperation):
    """
    Returns a column/Series of equal constant values, with length equal to that of input DataFrame
    Provided value can be static or callable which returns a value (e.g. from ContextValue)
    """
    calling_translations = {
        'dataframe': 'column',
        'column': 'column',
    }

    def __init__(self, value):
        """

        :param value: static value or callable which returns scalar value
        """
        self.value = value

    def __call__(self, vector):
        """

        :param vector: Dataframe or Series
        :return:
        """
        repeated_value = self.value(vector) if callable(self.value) else self.value
        return pd.Series([repeated_value] * len(vector.index))

    def __str__(self):
        return 'Column with repeated value: {}'.format(self.value)