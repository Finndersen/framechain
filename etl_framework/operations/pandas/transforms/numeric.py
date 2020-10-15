import pandas as pd
from pandas.api.types import is_numeric_dtype
from etl_framework.operations import If
from .basic import AsType
from etl_framework.operations.pandas.base import ColumnOperation
import numpy as np


class Floor(ColumnOperation):
    """ Floor numeric values (round down)"""
    def action(self, value):
        return np.floor(value)


class ToNumeric(ColumnOperation):
    """
    Convert column to numeric, with downcast support
    Downcast does not work on nullable integer type (Int8-64) if it contains Null values (but does work if it doesnt)
    """
    changes_type = True

    def __init__(self, downcast='integer'):
        """

        :param str downcast: Downcast type. integer, signed, unsigned or float
        """
        self.downcast = downcast

    def action(self, column):
        return pd.to_numeric(column, downcast=self.downcast)


class ToInteger(ColumnOperation):
    """
    Convert column to Integer type
    Normally if source data for 'integer' field contains null values, pandas will convert Series type to float
    (normal integer type cannot represent null values)
    This converter changes dtype to new nullable integer type ('Int32'), if float conversion has occurred
    Also performs automatic downcasting of non-null integer data to reduce memory
    """
    changes_type = True

    def __init__(self, large=False):
        """

        :param bool large: Whether to convert to 64 bit integer (True) or 32 bit (False)
        """
        int_type = 'Int64' if large else 'Int32'
        self.converter = If(lambda s: not s.isnull().all(),
                            If(lambda s: is_numeric_dtype(s.dtype),
                               AsType(int_type),                    # Float or other numeric to nullable int
                               ToNumeric() >> AsType(int_type)))    # First convert non-numeric to numeric

    def action(self, column):
        return self.converter(column)