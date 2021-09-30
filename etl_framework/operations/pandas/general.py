from etl_framework.operations import Operation
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
        super().__init__()
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


class Apply(Operation):
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
        super().__init__()
        self.operation = self.wrap_operation(operation)

    def action(self, vector):
        """
        :param vector: Dataframe or Column (series)
        :return:
        """
        if isinstance(vector, pd.DataFrame):
            return vector.apply(lambda row: self.run_wrapped_operation(self.operation, row),
                                axis=1)
        elif isinstance(vector, pd.Series):
            return vector.apply(lambda value: self.run_wrapped_operation(self.operation, value))
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

    def __init__(self, condition, operation):
        """

        :param condition: Callable which takes Dataframe or column and returns boolean series mask
        :param operation: Operation to pass masked column to
        """

        super().__init__(operation, condition=condition)

    def action(self, df_or_column_original):

        # Get mask using condition (should be read-only operation)
        mask = self.get_mask(df_or_column_original)

        # Exit early if mask does not match any values (unless input is DF cause transform may add extra empty columns)
        if isinstance(df_or_column_original, pd.Series) and not mask.any():
            return df_or_column_original

        # Make copy to avoid making changes to original Series or DF (deep copy if Series)
        df_or_column_copy = df_or_column_original.copy(deep=isinstance(df_or_column_original, pd.Series))

        # Provide masked data to operation. Make copy to avoid SettingWithCopyWarning
        transformed_values = self.run_wrapped_operation(self.operation, df_or_column_copy.loc[mask].copy())
        # Integrate values back into original Dataframe or column
        df_or_column_copy.loc[mask] = transformed_values

        if isinstance(df_or_column_copy, pd.DataFrame):
            # Add in any extra columns that may have been added to masked Dataframe
            for column_name in transformed_values.columns:
                if column_name not in df_or_column_copy.columns:
                    df_or_column_copy.loc[mask, column_name] = transformed_values[column_name]
            # Filter out any fully null rows in case DeleteRows operation was applied to masked content
            df_or_column_copy.dropna(how='all', inplace=True)

        return df_or_column_copy

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

    def __init__(self, value, dtype=None):
        """

        :param value: static value or callable which returns scalar value
        :param dtype: set dtype of column
        """
        super().__init__()
        self.value = value
        self.dtype = dtype

    def action(self, vector):
        """

        :param vector: Dataframe or Series
        :return:
        """
        repeated_value = self.value(vector) if callable(self.value) else self.value
        return pd.Series([repeated_value] * len(vector.index), index=vector.index, dtype=self.dtype)

    def description(self):
        desc = 'Column with value: "{}"'.format(self.value)
        if self.dtype:
            desc += ' and dtype: "{}"'.format(self.dtype)
        return desc


class FillNA(Operation):
    """
    Fill NA values of column or DF with specified value
    """
    def __init__(self, value):
        """

        :param value: static value or callable which returns scalar value
        """
        super().__init__()
        self.value = value

    def action(self, df_or_series):
        """

        :param df_or_series: Dataframe or Series
        :return:
        """
        return df_or_series.fillna(self.value)

    def description(self):
        return 'Fill NA values with: {}'.format(self.value)


class Min(Operation):
    """
    Get minimum value of Series (scalar value) or row-wise minimum of Dataframe (Series of minimums for each row)
    """
    def __init__(self, axis=None):
        """

        :param int axis: Axis to find minimum of (0 for column-wise min, 1 for row-wise)
        """
        super().__init__()
        self.axis = axis

    def action(self, df_or_series):
        """

        :param pd.DataFrame df_or_series:
        :return:
        """
        # Default to axis=1 for DF
        if isinstance(df_or_series, pd.DataFrame) and self.axis is None:
            axis = 1
        else:
            axis = self.axis

        return df_or_series.min(axis=axis)


class Max(Min):
    """
    Get maximum value of Series (scalar value) or row-wise maximum of Dataframe (Series of maximums for each row)
    """

    def action(self, df_or_series):
        """

        :param pd.DataFrame df_or_series:
        :return:
        """
        # Default to axis=1 for DF
        if isinstance(df_or_series, pd.DataFrame) and self.axis is None:
            axis = 1
        else:
            axis = self.axis

        return df_or_series.max(axis=axis)


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
        super().__init__()
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

