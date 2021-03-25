from etl_framework.operations.base import Operation, CompoundOperation
from etl_framework.operations.general import Map
from etl_framework.exceptions import ETLConfigurationError
import pandas as pd
from etl_framework.operations.pandas.base import ColumnOperation, ConditionallyAppliedOperation
import itertools


class Field(Operation):
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

    def action(self, multiple_fields):
        """
        :param multiple_fields: Dataframe or Row containing multiple fields
        return:
        """
        return multiple_fields[self.field_name]

    def description(self):
        return 'Field: "{}"'.format(self.field_name)


class ColumnMap(Map, ColumnOperation):
    """
    Provide mapping dictionary which will be used to Convert column values
    Can specify logic for what happens when lookup values are missing (raise error, pass through key, use default)
    """

    def action(self, value):
        """Apply mapping to column or value"""
        return value.map(self.mapping)


class Apply(CompoundOperation):
    """
    Wrapper which translates input from vector to scalar in Column axis
    e.g. Dataframe - > rows or Series -> values
    """
    wrapping_translations = {
        'dataframe': 'row',
        'column': 'value'
    }

    calling_translations = {
        'dataframe': 'column',
        'column': 'column'
    }

    def __init__(self, operation):
        """
        :param operation: Operation to apply to each element of vector
        """
        self.operation = operation
        super().__init__(self.operation)

    def action(self, vector):
        """
        :param vector: Dataframe or Column (series)
        :return:
        """
        if isinstance(vector, pd.DataFrame):
            return vector.apply(lambda row: self.operation(row), axis=1, result_type='reduce')
        elif isinstance(vector, pd.Series):
            return vector.apply(lambda value: self.operation(value))
        else:
            self.error(TypeError, 'Input should be DataFrame or Series')

    def description(self):
        return 'Apply to each row: ({}) '.format(self.operation)


class Mask(ConditionallyAppliedOperation):
    """
    Masking wrapper which takes Dataframe or Column, applies conditional logic to produce mask,
    and passes masked content to wrapped operation, and then integrates result back into original input
    It is possible to use operations to delete rows of a masked DF (e.g. using DeleteRows),
    however it is not recommended and does not have good performance
    """
    wrapping_translations = calling_translations = {'column': 'column', 'dataframe': 'dataframe'}

    def __init__(self, condition, operation):
        """

        :param condition: Callable which takes Dataframe or column and returns boolean series mask
        :param operation: Operation to pass masked column to
        """

        super().__init__(operation, condition=condition)

    def action(self, df_or_column):
        # Get mask using condition
        mask = self.condition(df_or_column)
        if mask is not None and not pd.api.types.is_bool_dtype(mask):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))
        # Provide masked data to operation. Make copy to avoid SettingWithCopyWarning
        transformed_values = self.operation(df_or_column.loc[mask].copy())
        # Integrate values back into original Dataframe or column
        df_or_column.loc[mask] = transformed_values

        if isinstance(df_or_column, pd.DataFrame):
            # Add in any extra columns that may have been added to masked Dataframe
            for column_name in transformed_values.columns:
                if column_name not in df_or_column.columns:
                    df_or_column.loc[mask, column_name] = transformed_values[column_name]
            # Filter out any fully null rows in case DeleteRows operation was applied to masked content
            df_or_column.dropna(how='all', inplace=True)

        return df_or_column

    def description(self):
        return 'Mask with condition ({}) and apply ({})'.format(self.condition, self.operation)

    def short_description(self):
        return 'Apply operation with mask condition ({})'.format(self.condition)


class ColumnOfValue(Operation):
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

    def action(self, vector):
        """

        :param vector: Dataframe or Series
        :return:
        """
        repeated_value = self.value(vector) if callable(self.value) else self.value
        return pd.Series([repeated_value] * len(vector.index), index=vector.index)

    def description(self):
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

    def action(self, column):
        """

        :param column: Dataframe or Series
        :return:
        """
        return column.fillna(self.value)

    def description(self):
        return 'Fill NA columns with: {}'.format(self.value)


class MergeRowValues(Operation):
    """
    Merges values across multiple fields in a row Series. Works similar to Series.combine but can operate over more than
    2 fields
    Define function for merge behavior and filter behavior

    merge_function: Function to merge row values. Takes field values as positional args, return single value
                    Merges values into list by default
    filter_function: Filter function to ignore field values, takes field value and returns False if value should be
                    ignored. Ignores null values by default
    Input: Series (row)
    Output: Merged set of values or None
    """

    def to_list(*args):
        return args

    def merge_lists(*args):
        return list(itertools.chain(*args))

    def __init__(self, *field_names, merge_function=to_list, filter_function=pd.isna):
        """

        :param str field_names: Sequence of field names to merge
        :param func merge_function: Function to merge row values. Takes field values as positional args, return single value
                Merges values into list by default
        :param func filter_function: Filter function to ignore field values, takes field value and returns False if value
        should be ignored. Ignores null values by default
        """
        if len(field_names) < 2:
            raise ValueError('Must provide at least 2 field names')
        self.field_names = field_names
        self.merge_function = merge_function
        self.filter_function = filter_function

    def action(self, row):
        # Get list of sets to merge
        values = [row[field_name] for field_name in self.field_names if not self.filter_function(row[field_name])]
        if not values:
            return None
        return self.merge_function(*values)

    def description(self):
        return 'Merge [{}] row values using function: "{}"'.format(', '.join(self.field_names),
                                                                   self.merge_function)

