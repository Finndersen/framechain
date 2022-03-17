import pandas as pd

from etl_framework.exceptions import OperationConfigurationError
from etl_framework.operations.pandas.base import ColumnOperation


class StringToInteger(ColumnOperation):
    """
    Convert a column of strings to integer
    """

    def action(self, column):
        return pd.to_numeric(column)

    def description(self):
        return 'Convert to numeric'


class AsType(ColumnOperation):
    """
    Convert type of column
    """

    def __init__(self, to_type, ignore_errors=False, copy=True, allow_str=False):
        """
        (be very careful setting copy=False as changes to values then may propagate to other pandas objects).
        :param str, type to_type:
        :param bool ignore_errors:
        :param bool copy: Whether to return copy of Series
        :param bool allow_str: Whether to allow conversion to str type
        """
        super().__init__()
        if to_type in {str, 'str'} and not allow_str:
            raise OperationConfigurationError('Doing .astype(str) can lead to unexpected behaviour like turning NA values into valid strings and is not recommended')
        self.to_type = to_type
        self.ignore_errors = ignore_errors
        self.copy = copy

    def action(self, column):
        return column.astype(self.to_type,
                             copy=self.copy,
                             errors='ignore' if self.ignore_errors else 'raise')

    def description(self):
        return 'Convert type to {}'.format(self.to_type)


class ToList(ColumnOperation):
    """
    Convert an input Series to list
    """
    def action(self, series):
        # .values.tolist() is faster than .to_list()
        return series.values.tolist()


class ToArray(ColumnOperation):
    """
    Convert an input Series to underlying Numpy array
    """
    def action(self, series):
        return series.values


