"""
Primary Pandas operations which take Dataframe and return Dataframe
"""
import logging

from etl_framework.operations import Operation
from .base import DataframeOperation

log = logging.getLogger(__name__)


class DeleteRows(DataframeOperation):
    """
    Operation used to filter DF on provided condition
    """

    def __init__(self, condition):
        """
        :param callable condition: Condition to filter row on. Takes DF and returns boolean mask
        """
        super().__init__()
        self.condition = self.wrap_operation(condition, wrap_value=False)

    def action(self, dataframe):
        # Get masked/filtered DF
        filtered_df = dataframe.loc[~self.run_wrapped_operation(self.condition, dataframe)]
        log.debug('Filtered out {} rows ({} remaining)'.format(len(dataframe.index) - len(filtered_df.index),
                                                               len(filtered_df.index)))
        # Return copy so that it is not a slice (which may raise SettingWithCopyWarning)
        return filtered_df.copy()

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

    def __init__(self, **rename_mapping):
        """

        :param str rename_mapping: mapping of old column names to new ones
        """
        super().__init__()
        self.rename_mapping = rename_mapping

    def action(self, dataframe):
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

    def __init__(self, first_column, second_column):
        """

        :param str first_column: First field to combine
        :param str second_column: Second field to combine
        """
        super().__init__()
        self.first_column = first_column
        self.second_column = second_column

    def action(self, dataframe):
        return dataframe[self.first_column].combine_first(dataframe[self.second_column])

    def description(self):
        return 'Combine "{}" and "{}" using first non-NaN value'.format(self.first_column, self.second_column)


class SetColumnOrder(DataframeOperation):
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
        return "Set column order: {}".format(self.columns)
