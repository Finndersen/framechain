from etl_framework.operations.pandas.base import ColumnOperation
from etl_framework.operations.transforms.string import RegexExtract


class StringFunction(ColumnOperation):
    """
    Call arbitrary Series string function
    """
    def __init__(self, func_name, *args, **kwargs):
        """

        :param str func_name: Name of string function to call
        :param args: Positional arguments to provide
        :param kwargs: Keyword arguments to provide
        """
        super().__init__()
        self.func_name = func_name
        self.args = args
        self.kwargs = kwargs

    def action(self, string_column):
        func = getattr(string_column.str, self.func_name)
        return func(*self.args, **self.kwargs)

    def description(self):
        desc = 'String Series function: "{}"'.format(self.func_name)
        if self.args:
            desc += ' with args: {}'.format(self.args)
        if self.kwargs:
            desc += ' and kwargs: {}'.format(self.kwargs)
        return desc


class StringColumnSplit(ColumnOperation):
    """
    Perform vectorised string split
    Splits string column into list of values
    If expand=True, returns Dataframe with columns of values
    """
    def __init__(self, pat=None, n=-1, expand=False, right=False):
        """
        :param str pat: String or regular expression to split on. If not specified, split on whitespace.
        :param int n:
        :param bool expand:
        :param bool right: Whether to split on right side
        """
        super().__init__()
        self.pat = pat
        self.n = n
        self.expand = expand
        self.right = right

    def action(self, string_column):
        if self.right:
            return string_column.str.rsplit(self.pat, n=self.n, expand=self.expand)
        else:
            return string_column.str.split(self.pat, n=self.n, expand=self.expand)

    def description(self):
        return '{} split string column on "{}"'.format('Right' if self.right else 'Left',
                                                       'whitespace' if self.pat is None else self.pat)


class Replace(ColumnOperation):
    """Perform vectorised string replacement"""

    def __init__(self, pattern, replace):
        """

        :param str or compiled regex pattern: Character sequence or regex pattern to replace
        :param str or callable replace: Replacement string or a callable. The callable is passed the regex match object
        and must return a replacement string to be used
        """
        super().__init__()
        self.pattern = pattern
        self.replace = replace

    def action(self, column):
        return column.str.replace(pat=self.pattern,
                                  repl=self.replace,
                                  regex=not isinstance(self.pattern, str))

    def description(self):
        return 'Replace "{}" with "{}"'.format(self.pattern, self.replace)


class Strip(ColumnOperation):
    """
    Strip whitespaces or other characters from string column
    """
    def __init__(self, strip_chars=None):
        """

        :param str strip_chars: Specifying the set of characters to be removed.
        All combinations of this set of characters will be stripped. If None then whitespaces are removed.
        """
        super().__init__()
        self.strip_chars = strip_chars

    def action(self, column):
        return column.str.strip(self.strip_chars)

    def description(self):
        if self.strip_chars:
            return 'Strip characters: "{}"'.format(self.strip_chars)
        else:
            return 'Strip whitespaces'


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
        super().__init__()
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
        super().__init__()
        self.delimiter = delimiter

    def action(self, string_series):
        return string_series.str.join(self.delimiter)

    def description(self):
        return 'Join strings with: "{}"'.format(self.delimiter)


class BytesColumnToString(ColumnOperation):
    """
    Decode column of bytes values into string
    """
    def __init__(self, encoding='utf-8'):
        """

        :param str encoding:
        """
        super().__init__()
        self.encoding = encoding

    def action(self, bytes_column):
        return bytes_column.str.decode(self.encoding)