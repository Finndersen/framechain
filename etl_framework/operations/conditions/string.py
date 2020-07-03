from etl_framework.operations import BaseOperation
import re

class StringContains(BaseOperation):
    """
    Test whether string value contains pattern or regex
    """
    def __init__(self, pattern, regex=False):
        """

        :param str pattern: search pattern
        :param bool regex: Whether pattern is regex
        """
        self.pattern = re.compile(pattern) if regex else pattern
        self.regex = regex

    def __call__(self, value):
        if self.regex:
            return self.pattern.search(value)
        else:
            return self.pattern in value


class StringIsNumeric(BaseOperation):
    """
    Test whether string value is numeric
    """
    def __call__(self, value):
        return value.isnumeric()