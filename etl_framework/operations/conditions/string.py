from etl_framework.operations import Operation
import re

class StringContains(Operation):
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

    def action(self, value):
        if self.regex:
            return self.pattern.search(value)
        else:
            return self.pattern in value


class StringIsNumeric(Operation):
    """
    Test whether string value is numeric
    """
    def action(self, value):
        return value.isnumeric()