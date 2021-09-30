import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from etl_framework.operations import If
from etl_framework.operations.pandas.base import ColumnOperation
from .conversions import AsType


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
        super().__init__()
        self.downcast = downcast
        self.errors = errors

    def action(self, column):
        return pd.to_numeric(column, downcast=self.downcast, errors=self.errors)


def ToNullableInteger(size=32):
    """
    Create transform to convert column to nullable Integer type
    Normally if source data for 'integer' field contains null values, pandas will convert Series type to float
    (normal integer type cannot represent null values)
    This converter changes dtype to new nullable integer type ('Int8-64'), if float conversion has occurred

    :param int size: Integer size in bits
    8: -128 to 127
    16: -32,768 to 32,767
    32: -2,147,483,648 to 2,147,483,647
    64: -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807
    :param bool ignore_errors: If true, any non-numeric input values that fail to convert to Numeric will be set as NaN
    """
    valid_sizes = [8, 16, 32, 64]

    if size not in valid_sizes:
        raise ValueError('Invalid integer bit size: {} Choose from: {}'.format(size, valid_sizes))

    return ToNumeric() >> AsType('Int{}'.format(size))
