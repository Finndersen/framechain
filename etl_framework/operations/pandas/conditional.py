"""
Operations which perform a conditional check and return a boolean Series column
"""
import pandas as pd

from etl_framework.exceptions import ETLConfigurationError
from etl_framework.operations import BaseOperation
from etl_framework.operations.pandas.base import ColumnOperation


class ValueIn(ColumnOperation):
    """
    Condition to select rows with column values in specified collection
    Input: Series
    Output: Boolean Series
    e.g.
    ValueIn(['red', 'brown', 'blonde'])

    """

    def __init__(self, values):
        """

        :param list/tuple/set values: Values to match on
        """
        self.equate_values = values

    def __call__(self, column):
        return column.isin(self.equate_values)

    def __str__(self):
        return ' values in {}'.format(self.equate_values)


class IsNull(ColumnOperation):
    """
    Select rows which are NA (None or np.NaN)
    """

    def __call__(self, column):
        return column.isna()

    def __str__(self):
        return ' is Null'


class StringContains(ColumnOperation):
    """
    Test whether string column values contain pattern or regex
    """
    def __init__(self, pattern, regex=False):
        """

        :param str pattern: search pattern
        :param bool regex: Whether pattern is regex
        """
        self.pattern =  pattern
        self.regex = regex

    def __call__(self, value):
        return value.str.contains(self.pattern, regex=self.regex)


class IsNumeric(ColumnOperation):
    """
    Test whether string column values are numeric
    """
    def __call__(self, value):
        return value.str.isnumeric()


class FieldExists(BaseOperation):
    """
    Check whether column exists in DataFrame
    """

    def __init__(self, field_name):
        """

        :param field_name: Name of column to select
        """
        if not isinstance(field_name, str):
            self.error(ETLConfigurationError, 'Field name must be string')
        self.field_name = field_name

    def __call__(self, multiple_fields):
        """
        :param multiple_fields: Dataframe or Row containing multiple fields
        return:
        """
        # Make copy of column to avoid SettingWithCopyWarning
        if isinstance(multiple_fields, pd.DataFrame):
            return self.field_name in multiple_fields.columns
        elif isinstance(multiple_fields, pd.Series):
            return self.field_name in multiple_fields.index
        else:
            self.error(ValueError, 'Expected Series or Dataframe, not "{}"'.format(multiple_fields))

    def __str__(self):
        return 'Field "{}" exists'.format(self.field_name)