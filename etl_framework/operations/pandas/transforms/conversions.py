import pandas as pd
from etl_framework.operations.pandas.base import ColumnOperation


class StringToInteger(ColumnOperation):
    """
    Convert a column of strings to integer
    """
    changes_type = True

    def action(self, column):
        return pd.to_numeric(column)

    def description(self):
        return 'Convert to numeric'


class AsType(ColumnOperation):
    """Convert type of column"""
    changes_type = True

    def __init__(self, to_type, ignore_errors=False):
        """

        :param str (numpy type) or python type to_type:
        """
        self.to_type = to_type
        self.ignore_errors = ignore_errors

    def action(self, column):
        return column.astype(self.to_type, errors='ignore' if self.ignore_errors else 'raise')

    def description(self):
        return 'Convert type to {}'.format(self.to_type)


