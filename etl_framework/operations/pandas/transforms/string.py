from etl_framework.operations.pandas.base import ColumnOperation
from etl_framework.operations.transforms.string import RegexExtract
import re


class Replace(ColumnOperation):
    """Perform vectorised string replacement"""

    def __init__(self, pattern, replace):
        """

        :param str or compiled regex pattern: Character sequence or regex pattern to replace
        :param str or callable replace: Replacement string or a callable. The callable is passed the regex match object and must return a replacement string to be used
        """
        self.pattern = pattern
        self.replace = replace

    def action(self, column):
        return column.str.replace(pat=self.pattern,
                                  repl=self.replace,
                                  regex=not isinstance(self.pattern, str))

    def description(self):
        return 'Replace "{}" with "{}"'.format(self.pattern, self.replace)


class StripWhitespaces(ColumnOperation):
    """
    Strip whitespaces from string column
    """

    def action(self, column):
        return column.str.strip()


class StringLength(ColumnOperation):
    """
    Calaculate string length of column
    """
    def action(self, value):
        """

        :param value: Either string column or scalar value
        :return:
        """
        return value.str.len()

    def description(self):
        return 'len()'


class ColumnRegexExtract(RegexExtract):
    """
    Extract text from a string series using regex pattern, return a single series of extracted values
    Pattern should have a single capture group
    Will return NA for any values that do not match the regex
    """

    def action(self, string_series):
        return string_series.str.extract(self.compiled_pattern.pattern, expand=False, **self.flags)


class ColumnRegexFindall(ColumnOperation):
    """
    Vectorised equivalent of re.findall() for string column
    Each result value will be a list of matches from the original string
    """
    def __init__(self, pattern, **flags):
        """

        :param str pattern: Regex pattern to match on
        :param flags: Extra flags for regex library
        """
        self.flags = flags
        self.pattern = pattern

    def action(self, string_series):
        return string_series.str.findall(self.pattern, **self.flags)

    def description(self):
        return 'RegexFindall with pattern: "{}"'.format(self.pattern)


class StringColumnJoin(ColumnOperation):
    """
    Join lists contained as elements in the Series/Index with passed delimiter.
    Vectorised equivalent of str.join()
    """
    def __init__(self, delimiter):
        """

        :param sr delimiter: Delimiter to use for join
        """
        self.delimiter = delimiter

    def action(self, string_series):
        return string_series.str.join(self.delimiter)

    def description(self):
        return 'Join strings with: "{}"'.format(self.delimiter)