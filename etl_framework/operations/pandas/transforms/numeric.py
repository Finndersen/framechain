import pandas as pd
from pandas.api.types import is_numeric_dtype
from etl_framework.operations import If
from .conversions import AsType
from etl_framework.operations.pandas import FillNA
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

    def __init__(self, downcast='integer', errors='raise'):
        """

        :param str downcast: Downcast type. integer, signed, unsigned or float
        :param str errors: Error handling behaviour. {‘ignore’, ‘raise’, ‘coerce’}
        If ‘raise’, then invalid parsing will raise an exception.
        If ‘coerce’, then invalid parsing will be set as NaN.
        If ‘ignore’, then invalid parsing will return the input.
        """
        self.downcast = downcast
        self.errors = errors

    def action(self, column):
        return pd.to_numeric(column, downcast=self.downcast, errors=self.errors)


class ToInteger(ColumnOperation):
    """
    Convert column to Integer type
    Normally if source data for 'integer' field contains null values, pandas will convert Series type to float
    (normal integer type cannot represent null values)
    This converter changes dtype to new nullable integer type ('Int32'), if float conversion has occurred
    Also performs automatic downcasting of non-null integer data to reduce memory
    """
    changes_type = True

    def __init__(self, large=False, ignore_errors=False):
        """

        :param bool large: Whether to convert to 64 bit integer (True) or 32 bit (False)
        :param bool ignore_errors: Whether to ignore casting errors
        """
        int_type = 'Int64' if large else 'Int32'
        self.converter = If(lambda s: not s.isnull().all(),
                            If(lambda s: is_numeric_dtype(s.dtype),
                               # Float or other numeric to nullable int
                               AsType(int_type, ignore_errors=ignore_errors),
                               # First convert non-numeric to numeric
                               ToNumeric(errors='coerce' if ignore_errors else 'raise') >> AsType(int_type,
                                                                                                  ignore_errors=ignore_errors)))

    def action(self, column):
        return self.converter(column)