import re

from etl_framework.operations import Operation


class In(Operation):
    """
    Used to implement 'in' operator
    """

    def __init__(self, collection):
        """

        :param collection: Collection of values or object to test if value is included in
        """
        self.collection = set(collection)

    def action(self, value):
        return value in self.collection

    def description(self):
        return 'Value is in: {}'.format(self.collection)


class Is(Operation):
    """
    Used to implement 'is' operator
    """

    def __init__(self, other_value):
        """

        :param other_value: Other value to compare to
        """
        self.other_value = other_value

    def action(self, value):
        return value is self.other_value

    def description(self):
        return 'Value is: {}'.format(self.other_value)


class StringContains(Operation):
    """
    Test whether string value contains pattern or regex
    """
    def __init__(self, pattern, is_regex=False):
        """

        :param str pattern: search pattern
        :param bool is_regex: Whether pattern is regex
        """
        self.pattern = re.compile(pattern) if is_regex else pattern
        self.is_regex = is_regex

    def action(self, value):
        if self.is_regex:
            return bool(self.pattern.search(value))
        else:
            return self.pattern in value

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
        self.instance_type = instance_type

    def action(self, value):
        return isinstance(value, self.instance_type)

    def description(self):
        return 'IsInstance: "{}"'.format(self.instance_type)