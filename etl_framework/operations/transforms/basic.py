import pandas as pd
from etl_framework.operations.base import ColumnOperation
from etl_framework.operations.conditions import If


class StringToInteger(ColumnOperation):
    """
    Convert a column of strings to integer
    """
    changes_type = True

    def __call__(self, column):
        return pd.to_numeric(column)

    def __str__(self):
        return 'Convert to numeric'


class ConvertType(ColumnOperation):
    """Convert type of column"""
    changes_type = True

    def __init__(self, to_type):
        """

        :param str (numpy type) or python type to_type:
        """
        self.to_type = to_type

    def __call__(self, column):
        return column.astype(self.to_type)

    def __str__(self):
        return 'Convert type to {}'.format(self.to_type)


class DowncastNumber(ColumnOperation):
    """
    Downcast number column to smallest possible size
    Downcast does not work on nullable integer type (Int8-64) if it contains Null values (but does work if it doesnt)
    """
    changes_type = True

    def __init__(self, downcast='integer'):
        """

        :param str downcast: Downcast type. integer, signed, unsigned or float
        """
        self.downcast = downcast

    def __call__(self, column):
        return pd.to_numeric(column, downcast=self.downcast)


class ToInteger(ColumnOperation):
    """
    If source data for 'integer' field contains null values, pandas will convert Series type to float
    (normal integer type cannot represent null values)
    This converter changes dtype to new nullable integer type ('Int32'), if float conversion has occurred
    Also performs automatic downcasting of non-null integer data to reduce memory
    """
    changes_type = True

    def __init__(self, int_size=32):
        self.converter = If(lambda s: not s.isnull().all(),
                            If(lambda s: 'float' in str(s.dtype),
                               ConvertType('Int{}'.format(int_size)),
                               DowncastNumber()))

    def __call__(self, column):
        return self.converter(column)
