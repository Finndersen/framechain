import itertools

import pandas as pd

from etl_framework.operations import Operation
from etl_framework.operations.general import MapValue
from etl_framework.operations.pandas.base import ColumnOperation, DataframeOperation
from etl_framework.operations.pandas.exceptions import InvalidColumnError, OperationConfigurationError


class Column(DataframeOperation):
    """
    Operation used to select a column of a Dataframe or a field value of a Row
    """
    def __init__(self, column_name):
        """

        :param column_name: Name of column to select
        """
        super().__init__()
        if not isinstance(column_name, str):
            self.error(OperationConfigurationError, 'Field name must be string')
        self.column_name = column_name

    def action(self, df_or_series):
        """
        :param df_or_series: Dataframe or Row containing multiple fields
        return:
        """
        if isinstance(df_or_series, pd.DataFrame):
            if self.column_name not in df_or_series.columns:
                raise InvalidColumnError('"{}" is not in DataFrame columns: {}'.format(self.column_name,
                                                                                       df_or_series.columns))
        elif isinstance(df_or_series, pd.Series):
            if self.column_name not in df_or_series.index:
                raise InvalidColumnError('"{}" is not in Series index: {}'.format(self.column_name,
                                                                                       df_or_series.index))
        else:
            raise TypeError('Expected DataFrame or Series, not {}'.format(type(df_or_series)))

        return df_or_series[self.column_name]

    def description(self):
        return 'Column: "{}"'.format(self.column_name)

    def get_required_columns(self):
        return [self.column_name]


class MapColumnValues(MapValue, ColumnOperation):
    """
    Provide mapping dictionary which will be used to Convert column values
    Can specify logic for what happens when lookup values are missing (raise error, pass through key, use default)
    """

    def action(self, value):
        """Apply mapping to column or value"""
        return value.map(self.mapping)


class ColumnOfValue(Operation):
    """
    Returns a column/Series of equal constant values, with length equal to that of input DataFrame
    """
    def __init__(self, value, dtype=object):
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
        return pd.Series([self.value] * len(vector.index), index=vector.index, dtype=self.dtype)

    def description(self):
        desc = 'Column with value: "{}"'.format(self.value)
        if self.dtype:
            desc += ' and dtype: "{}"'.format(self.dtype)
        return desc


class FillNA(Operation):
    """
    Fill NA values of column or DF with specified value
    """

    def __init__(self, value, **kwargs):
        """

        :param value: static value or callable which returns scalar value
        :param kwarg: Keyword arguments to apply to fillna() method
        """
        super().__init__()
        self.value = value
        self.kwargs = kwargs

    def action(self, df_or_series):
        """

        :param df_or_series: Dataframe or Series
        :return:
        """
        return df_or_series.fillna(self.value, **self.kwargs)

    def description(self):
        return 'Fill NA values with: {}'.format(self.value)


class Min(Operation):
    """
    Get minimum value of Series (return scalar value) or row-wise minimum of Dataframe
    (return Series of minimums for each row)
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


class Copy(Operation):
    """
    Return copy of input DF or Series
    """
    def __init__(self, deep=False):
        """

        :param deep:
        """
        super().__init__()
        self.deep = deep

    def action(self, vector):
        """

        :param pd.DataFrame or pd.Series vector:
        :return:
        """
        return vector.copy(deep=self.deep)


class PrintDF(DataframeOperation):
    """
    Print contents of DataFrame and return input
    Useful for debugging
    """
    def __init__(self, message=None, columns=None, rows=15):
        """
        :param str message: Message to describe DF
        :param list columns: List of columns to print, otherwise all
        :param int rows: Number of rows to print
        """
        super().__init__()
        self.message = message
        self.columns = columns
        self.rows = rows

    def action(self, dataframe):
        """

        :param pd.DataFrame dataframe:
        :return:
        """
        if self.message:
            print(self.message)
        columns = self.columns or dataframe.columns
        pd.set_option('display.width', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_rows', self.rows)
        print(dataframe[columns])
        return dataframe

    def get_required_columns(self):
        return self.columns or self.ALL_COLUMNS