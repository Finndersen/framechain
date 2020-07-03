from etl_framework.operations.pandas.base import ColumnOperation


class Replace(ColumnOperation):
    """Perform vectorised string replacement"""

    def __init__(self, pattern, replace):
        """

        :param str or compiled regex pattern: Character sequence or regex pattern to replace
        :param str or callable replace: Replacement string or a callable. The callable is passed the regex match object and must return a replacement string to be used
        """
        self.pattern = pattern
        self.replace = replace

    def __call__(self, column):
        return column.str.replace(pat=self.pattern,
                                  repl=self.replace,
                                  regex=not isinstance(self.pattern, str))

    def __str__(self):
        return 'Replace "{}" with "{}"'.format(self.pattern, self.replace)


class StripWhitespaces(ColumnOperation):
    """
    Strip whitespaces from string column
    """

    def __call__(self, column):
        return column.str.strip()


class StringLength(ColumnOperation):
    """
    Calaculate string length of column
    """
    def __call__(self, value):
        """

        :param value: Either string column or scalar value
        :return:
        """
        return value.str.len()

    def __str__(self):
        return 'len()'