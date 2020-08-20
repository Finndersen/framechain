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
            self.error(ETLConfigurationError, 'Field name must be string')
        self.field_name = field_name

    def __call__(self, multiple_fields):
        """
        :param multiple_fields: Dataframe or Row containing multiple fields
        return:
        """
        return multiple_fields[self.field_name]

    def __str__(self):
        return 'Field: "{}"'.format(self.field_name)


class FieldExists(BaseOperation):
    """
    Check whether column exists in DataFrame
    """

    def __init__(self, field_name):
        """

        :param field_name: Name of column to select
        """
        if not isinstance(field_name, str):
            self.error(ETLConfigurationError, 'Field name must be string')
        self.field_name = field_name

    def __call__(self, multiple_fields):
        """
        :param multiple_fields: Dataframe or Row containing multiple fields
        return:
        """
        # Make copy of column to avoid SettingWithCopyWarning
        if isinstance(multiple_fields, pd.DataFrame):
            return self.field_name in multiple_fields.columns
        elif isinstance(multiple_fields, pd.Series):
            return self.field_name in multiple_fields.index
        else:
            self.error(ValueError, 'Expected Series or Dataframe, not "{}"'.format(multiple_fields))

    def __str__(self):
        return 'Field "{}" exists'.format(self.field_name)


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
            return vector.apply(lambda row: self.operation(row), axis=1, result_type='reduce')
        elif isinstance(vector, pd.Series):
            return vector.apply(lambda value: self.operation(value))
        else:
            self.error(ValueError, 'Input should be DataFrame or Series')

    def __str__(self):
        return 'Apply to each row: ({}) '.format(self.operation)


class Mask(OperationWrapper):
    """
    Masking wrapper which takes Dataframe or Column, applies conditional logic to produce mask,
    and passes masked content to wrapped operation, and then integrates result back into original input
    """
    wrapping_translations = calling_translations = {'column': 'column', 'dataframe': 'dataframe'}

    def __init__(self, condition, operation):
        """

        :param condition: Callable which takes Dataframe or column and returns boolean series mask
        :param operation: Operation to pass masked column to
        """
        # Validate type compatability of condition
        # if self.condition_input_type not in TypeTranslations.get_for_operation(condition):
        #     self.error(ETLConfigurationError, 'Condition: {} is not compatible'.format(condition))
        self.condition = condition
        super().__init__(operation)

    def __call__(self, df_or_column):
        # Get mask using condition
        mask = self.condition(df_or_column)
        if mask is not None and not (isinstance(mask, pd.Series) and mask.dtype == bool):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))
        # Provide masked data to operation. Make copy to avoid SettingWithCopyWarning
        transformed_values = self.operation(df_or_column.loc[mask].copy())
        # Integrate values back into original Dataframe or column
        df_or_column.loc[mask] = transformed_values

        if isinstance(df_or_column, pd.DataFrame):
            # Filter out any fully null rows in case DeleteRows operation was applied to masked content
            df_or_column.dropna(how='all', inplace=True)
            # Add in any extra columns that may have been added to masked Dataframe
            for column_name in transformed_values.columns:
                if column_name not in df_or_column.columns:
                    df_or_column.loc[mask, column_name] = transformed_values[column_name]

        return df_or_column

    def __str__(self):
        return 'Mask with condition ({}) and apply ({})'.format(self.condition, self.operation)


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
        return 'Column with value: "{}"'.format(self.value)


class FillNA(ColumnOperation):
    """
    Fill NA values of column with specified value
    """
    def __init__(self, value):
        """

        :param value: static value or callable which returns scalar value
        """
        self.value = value

    def __call__(self, column):
        """

        :param column: Dataframe or Series
        :return:
        """
        return column.fillna(self.value)


