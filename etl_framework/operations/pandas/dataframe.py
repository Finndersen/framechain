"""
Primary Pandas operations which take Dataframe and return Dataframe
"""
import logging
import pandas as pd

from . import Column
from .base import DataframeOperation
from etl_framework.operations import Operation

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
        drop_mask = self.condition(dataframe)
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

    def get_required_columns(self):
        return self.columns


class RenameColumns(DataframeOperation):
    """
    Operation for renaming columns.
    Rename mapping can be provided as either keyword arguments, or dictionary to 'mapping' argument
    """

    def __init__(self, mapping=None, error_if_missing=True, **rename_mapping):
        """
        :param bool error_if_missing: Whether to raise exception if field name in mapping does not exist
        :param str rename_mapping: mapping of old column names to new ones
        """
        super().__init__()
        self.rename_mapping = mapping or rename_mapping
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

    def get_required_columns(self):
        return self.columns


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
        return 'Combine "{}" and "{}" using: {}'.format(self.column1_name, self.column2_name,
                                                        self.func)

    def get_required_columns(self):
        return [self.column1_name, self.column2_name]


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
        self.first_operation = self.add_child_operation(Column(first_operation)
                                                        if isinstance(first_operation, str)
                                                        else first_operation)
        self.second_operation = self.add_child_operation(Column(second_operation)
                                                         if isinstance(second_operation, str)
                                                         else second_operation)

    def action(self, dataframe):
        first_column = self.first_operation(dataframe)
        second_column = self.second_operation(dataframe)

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

    def get_required_columns(self):
        return self.columns


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
            if not isinstance(column.dtype, pd.CategoricalDtype):
                raise TypeError('"{}" is not a categorical type column ({})'.format(column_name,
                                                                                    column.dtype))

            all_categories = all_categories.union(column.cat.categories)

        # Set new categories on all columns
        for column_name in self.category_columns:
            dataframe[column_name] = dataframe[column_name].cat.set_categories(all_categories)

        return dataframe

    def get_required_columns(self):
        return self.category_columns


class CreateDuplicateRows(DataframeOperation):
    """Create a new data frame by joining original dataframe and part of original dataframe based on condition.
    Usage data = pd.DataFrame([{'a':1, 'b':2}, {'b':1}, {'a':1}, {'a':1, 'b':1}])
                CreateDuplicateRows((Column('a')== Column('b')))(data)"""

    def __init__(self, condition):
        super().__init__()
        self.condition = self.add_child_operation(condition)

    def action(self, dataframe):
        mask = self.condition(dataframe)

        if not pd.api.types.is_bool_dtype(mask):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))

        if str(mask.dtype) == 'boolean':
            mask = mask.fillna(False).astype(bool)

        return pd.concat([dataframe, dataframe[mask]], ignore_index=True)

    def description(self):
        desc = 'Mask input with condition ({})'.format(self.condition)
        return desc


class Merge(Operation):
    """
    Merges two Dataframes, joining on values of specified column(s)
    """

    def __init__(self, on=None, left_on=None, right_on=None, join='inner', verify_dtypes=True,
                 **merge_kwargs):
        """
        If neither on, left_on or right_on are provided, will join on columns common between dataframes
        :param str/list on: column name(s) to join on both DataFrames (must exist in both)
        :param str/list left_on: column name(s) to join on left DataFrame, or 'index' to use index
        as join key
        :param str/list right_on: column name(s) to join on right DataFrame, or 'index' to use
        index as join key
        :param str join: Type of join to merge dataframes--> {‘left’, ‘right’, ‘outer’, ‘inner’, ‘cross’}
        :param bool verify_dtypes: Whether to verify that merge columns have the same dtype
        :param dict merge_kwargs: Additional arguments to pass to pd.DataFrame.merge method
        """
        super().__init__()
        # Validate config
        if on:
            if any([left_on, right_on]):
                raise ValueError('Cannot provide "on" parameter as well as either "left_on" or "right_on"')
            left_on = right_on = on

        if any([left_on, right_on]):
            if not all([left_on, right_on]):
                raise ValueError('Must provide either both left_on and right_on parameters, or neither')
        else:
            raise ValueError('Must provide both "left_on" and "right_on"')

        if isinstance(left_on, str) and left_on != 'index':
            left_on = [left_on]

        if isinstance(right_on, str) and right_on != 'index':
            right_on = [right_on]

        if left_on != 'index' and right_on != 'index' and len(left_on) != len(right_on):
            raise ValueError('"left_on" and "right_on" must have same length')

        self.join = join
        self.left_on = left_on
        self.right_on = right_on
        self.verify_dtypes = verify_dtypes
        self.merge_kwargs = merge_kwargs

    def action(self, left_dataframe, right_dataframe):
        """
        Merge two dataframes
        :param pd.DataFrame left_dataframe:
        :param pd.DataFrame right_dataframe:
        :return:
        """
        # Verify data types of join columns are the same
        if self.verify_dtypes and self.left_on != 'index' and self.right_on != 'index':
            for left_column, right_column in zip(self.left_on, self.right_on):
                if left_dataframe[left_column].dtype != right_dataframe[right_column].dtype:
                    raise TypeError('Dtypes of "{}"({}) and "{}"({}) are not equal'.format(left_column,
                                                                                           left_dataframe[left_column].dtype,
                                                                                           right_column,
                                                                                           right_dataframe[right_column].dtype))
        return left_dataframe.merge(right_dataframe,
                                    how=self.join,
                                    left_on=self.left_on if self.left_on != 'index' else None,
                                    right_on=self.right_on if self.right_on != 'index' else None,
                                    left_index=self.left_on == 'index',
                                    right_index=self.right_on == 'index',
                                    **self.merge_kwargs)

    def description(self):
        return 'Merges two dataframes via an {} join on the left dataframe {} and right ' \
               'dataframe {}'.format(self.join,
                                     'column(s): {}'.format(self.left_on) if self.left_on != 'index' else 'index',
                                     'column(s): {}'.format(self.right_on) if self.right_on != 'index' else 'index')