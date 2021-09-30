import pandas as pd
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

    def __init__(self, to_type, ignore_errors=False, copy=True):
        """
        (be very careful setting copy=False as changes to values then may propagate to other pandas objects).
        :param str, type to_type:
        :param bool ignore_errors:
        :param bool copy: Whether to return copy of Series
        """
        super().__init__()
        self.to_type = to_type
        self.ignore_errors = ignore_errors
        self.copy = copy

    def action(self, column):
        return column.astype(self.to_type,
                             copy=self.copy,
                             errors='ignore' if self.ignore_errors else 'raise')

    def description(self):
        return 'Convert type to {}'.format(self.to_type)


