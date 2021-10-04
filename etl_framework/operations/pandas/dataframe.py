"""
Primary Pandas operations which take Dataframe and return Dataframe
"""
import logging
import pandas as pd
from pandas.api.types import is_categorical_dtype

from . import Field
from .base import DataframeOperation

log = logging.getLogger(__name__)


class DropRows(DataframeOperation):
    """
    Operation used to filter DF on provided condition
    Implementation notes:
    When proportion of rows being dropped is minority, df.drop() is faster than df.loc[].copy()
    When proportion of rows being dropped is majority, df.drop() is slower than df.loc[].copy()
    """

    def __init__(self, condition):
        """
        :param callable condition: Condition to filter row on. Takes DF and returns boolean mask
        """
        super().__init__()
        self.condition = self.add_child_operation(condition, wrap_value=False)

    def action(self, dataframe):
        # Get masked/filtered DF
        drop_mask = self.run_child_operation(self.condition, dataframe)
        if not pd.api.types.is_bool_dtype(drop_mask):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))

        filtered_df = dataframe.drop(index=dataframe[drop_mask].index)
        # Reset index of new DF
        filtered_df.reset_index(inplace=True, drop=True)
        return filtered_df

    def description(self):
        return 'Delete rows which match condition: {}'.format(self.condition)


class DropColumns(DataframeOperation):
    """
    Used to drop columns from dataframe
    """

    def __init__(self, *columns, error_if_missing=True):
        """

        :param str columns: column names to drop
        :param bool error_if_missing: Whether to raise an error if any of specified columns are missing
        """
        super().__init__()
        if not all(isinstance(column_name, (str, int)) for column_name in columns):
            raise TypeError('Column labels must be string or integer')
        self.columns = list(columns)
        self.error_if_missing = error_if_missing

    def action(self, dataframe):
        return dataframe.drop(columns=self.columns, errors='raise' if self.error_if_missing else 'ignore')

    def description(self):
        return 'Drop columns: {}'.format(self.columns)


class RenameColumns(DataframeOperation):
    """
    Operation for renaming columns
    """

    def __init__(self, error_if_missing=True, **rename_mapping):
        """
        :param bool error_if_missing: Whether to raise exception if field name in mapping does not exist
        :param str rename_mapping: mapping of old column names to new ones
        """
        super().__init__()
        self.rename_mapping = rename_mapping
        self.error_if_missing = error_if_missing

    def action(self, dataframe):
        if self.error_if_missing:
            # Check if any provided mapping columns do not exist
            # (older pandas versions do not have 'errors' kwarg in df.rename())
            for column_name in self.rename_mapping.keys():
                if column_name not in dataframe.columns:
                    raise KeyError('Column "{}" does not exist in dataframe'.format(column_name))

        return dataframe.rename(columns=self.rename_mapping)

    def description(self):
        return 'Rename columns: {}'.format(self.rename_mapping)


class Sort(DataframeOperation):
    """
    Sort dataframe by columns
    """

    def __init__(self, sort_by, ascending=True):
        """

        :param sort_by: Name or list of names to sort by
        """
        super().__init__()
        self.sort_by = sort_by
        self.ascending = ascending

    def action(self, dataframe):
        return dataframe.sort_values(self.sort_by, ascending=self.ascending)

    def description(self):
        return 'Sort by: {}'.format(self.sort_by)


class MultipleFillNA(DataframeOperation):
    """
    Fill NA values of multiple specified columns with particular value
    """

    def __init__(self, columns, value):
        """
        :param str/list columns: List of column names or single column name
        :param value: static value or callable which returns scalar value
        """
        super().__init__()
        self.value = value
        if isinstance(columns, str):
            columns = [columns]
        self.columns = columns

    def action(self, dataframe):
        """

        :param dataframe: Dataframe or Series
        :return:
        """
        fill_value = self.value(dataframe) if callable(self.value) else self.value
        for column_name in self.columns:
            dataframe[column_name].fillna(fill_value)
        return dataframe

    def description(self):
        return 'Fill columns {} NA values with: "{}"'.format(self.columns, self.value)


class Explode(DataframeOperation):
    """
    Split rows into multiple rows using column which contains list-like values. E.g:
    df:
        A	        B
    0	[1, 2, 3]	a
    1	foo	        b
    2	[]	        c
    3	[3, 4]	    d

    df.explode('A'):
    	A	B
    0	1	a
    0	2	a
    0	3	a
    1	foo	b
    2	NaN	c
    3	3	d
    3	4	d

    This adds values and transforms the index so cannot be used on a masked dataframe (cannot be applied conditionally)
    Some operations will not work afterwards unless index is reset (e.g. DeleteRows within a conditional Mask)
    Note when exploding multiple times, reset_index=True should be used otherwise might get unwanted duplicates
    TODO: pandas 1.1.0 adds ignore_index which can be used instead of manually resetting
    """

    def __init__(self, column, reset_index=True):
        """

        :param str column: Column to apply explode on
        :param bool reset_index: Whether to reset index after exploding (removes duplicate index values)
        """
        super().__init__()
        self.column = column
        self.reset_index = reset_index

    def action(self, dataframe):
        df = dataframe.explode(self.column)
        if self.reset_index:
            # Assigning new index like this is faster than df.reset_index()
            df.index = range(len(df.index))
        return df

    def description(self):
        return 'Explode on field: "{}"'.format(self.column)


class Combine(DataframeOperation):
    """
    Combine values from two Series using func to perform elementwise selection for combined Series
    fill_value is assumed when value is missing at some index from one of the two objects being combined.
    the provided combine function can be constructed using chained Operations to allow for more complex filtering /
    conditional logic etc.
    """

    def __init__(self, column1_name, column2_name, func, fill_value=None):
        """

        :param str column1_name: First field to combine
        :param str column2_name: Second field to combine
        :param func: Function that takes two scalars as inputs and returns a combined element.
        :param fill_value:
        """
        super().__init__()
        self.column1_name = column1_name
        self.column2_name = column2_name
        self.func = func
        self.fill_value = fill_value

    def action(self, dataframe):
        return dataframe[self.column1_name].combine(dataframe[self.column2_name],
                                                    self.func,
                                                    fill_value=self.fill_value)

    def description(self):
        return 'Combine "{}" and "{}" using: {}'.format(self.column1_name, self.column2_name, self.func)


class CombineFirst(DataframeOperation):
    """
    Combine values of two Series using first non-NaN value
    """

    def __init__(self, first_operation, second_operation):
        """

        :param Operation, str first_operation: Operation which takes DF as input and produces first field to combine
        Can provide as column name string and will use Field() operation by default
        :param Operation, str second_operation: Operation which takes DF as input and produces second field to combine
        Can provide as column name string and will use Field() operation by default
        """
        super().__init__()
        self.first_operation = self.add_child_operation(Field(first_operation)
                                                        if isinstance(first_operation, str)
                                                        else first_operation)
        self.second_operation = self.add_child_operation(Field(second_operation)
                                                         if isinstance(second_operation, str)
                                                         else second_operation)

    def action(self, dataframe):
        first_column = self.run_child_operation(self.first_operation, dataframe)
        second_column = self.run_child_operation(self.second_operation, dataframe)

        if not isinstance(first_column, pd.Series):
            raise ValueError('Operation must return Series, not: {}'.format(type(first_column)))

        if not isinstance(second_column, pd.Series):
            raise ValueError('Operation must return Series, not: {}'.format(type(second_column)))

        return first_column.combine_first(second_column)

    def description(self):
        return 'Combine "{}" and "{}" using first non-NaN value'.format(self.first_operation, self.second_operation)


class SelectColumns(DataframeOperation):
    """
    Set column order or select subset of columns from dataframe
    """

    def __init__(self, columns):
        """

        :param list columns: List of column names
        """
        super().__init__()
        self.columns = columns

    def action(self, dataframe):
        return dataframe[self.columns]

    def description(self):
        return "Select columns: {}".format(self.columns)


class AlignCategories(DataframeOperation):
    """
    Align the categories of multiple Category type columns
    This will then allow other operations to be performed on the columns (e.g. CombineFirst)
    """
    def __init__(self, *category_columns):
        """

        :param category_columns:
        """
        if len(category_columns) < 2:
            raise ValueError('Must provide at least 2 column names')
        super().__init__()
        self.category_columns = category_columns

    def action(self, dataframe):
        all_categories = pd.Index([])
        # Validate column type and build aggregate category list
        for column_name in self.category_columns:
            column = dataframe[column_name]
            if not is_categorical_dtype(column):
                raise TypeError('"{}" is not a categorical type column ({})'.format(column_name,
                                                                                    column.dtype))

            all_categories = all_categories.union(column.cat.categories)

        # Set new categories on all columns
        for column_name in self.category_columns:
            dataframe[column_name] = dataframe[column_name].cat.set_categories(all_categories)

        return dataframe