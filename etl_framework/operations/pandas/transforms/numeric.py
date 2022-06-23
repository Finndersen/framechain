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
    Downcast does not work on nullable integer type (Int8-64) if it contains Null values
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


INTEGER_SIZES = [8, 16, 32, 64]


class ToNullableInteger(ColumnOperation):
    """
    Convert column to nullable Integer type
    Normally if source data for 'integer' field contains null values, pandas will convert Series type to float
    (normal integer type cannot represent null values)
    This converter changes dtype to new nullable integer type ('Int8-64'), if float conversion has occurred

    """
    def __init__(self, size=32):
        """

        :param int size: Integer size in bits
        8: -128 to 127
        16: -32,768 to 32,767
        32: -2,147,483,648 to 2,147,483,647
        64: -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807
        :param size:
        """
        super().__init__()
        if size not in INTEGER_SIZES:
            raise ValueError('Invalid integer bit size: {} Choose from: {}'.format(size, INTEGER_SIZES))
        self.size = size

    def action(self, number_column):
        # Convert to numeric if not already
        if number_column.dtype == object:
            number_column = pd.to_numeric(number_column, downcast='integer')

        try:
            return number_column.astype('Int{}'.format(self.size))
        except TypeError:
            # Try flooring values first if direct casting fails
            return np.floor(number_column).astype('Int{}'.format(self.size))

