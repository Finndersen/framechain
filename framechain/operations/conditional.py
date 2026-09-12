import re

from framechain.operations import Operation


class StringContains(Operation):
    """
    Test whether string value contains pattern or regex
    """
    def __init__(self, pattern, is_regex=False):
        """

        :param str pattern: search pattern
        :param bool is_regex: Whether pattern is regex
        """
        super().__init__()
        self.pattern = re.compile(pattern) if is_regex else pattern
        self.is_regex = is_regex

    def action(self, str_value):
        if self.is_regex:
            return bool(self.pattern.search(str_value))
        else:
            return self.pattern in str_value

    def description(self):
        return 'String contains: "{}"'.format(self.pattern)


class StringIsNumeric(Operation):
    """
    Test whether string value is numeric
    """
    def action(self, value):
        return value.isnumeric()


class IsInstance(Operation):
    """
    Check if value is a particular type
    """
    def __init__(self, instance_type):
        """

        :param instance_type:
        """
        super().__init__()
        self.instance_type = instance_type

    def action(self, value):
        return isinstance(value, self.instance_type)

    def description(self):
        return 'IsInstance: "{}"'.format(self.instance_type)


