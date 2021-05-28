from etl_framework.operations import Operation
import re


class RegexExtract(Operation):
    """
    Extract value from string using regex pattern with a single capture group
    Returns None if no match (unless original_if_no_match is set)
    """
    def __init__(self, pattern, original_if_no_match=False, **flags):
        """

        :param str or re.pattern pattern: Regex pattern to match on
        :param bool original_if_no_match: Whether to return original input string instead of None if it does not match
        :param flags: Extra flags for regex library
        """
        super().__init__()
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        # Validate pattern has only one capture group
        if pattern.groups != 1:
            raise ValueError('Regex pattern: "{}" should have only one capture group'.format(pattern.pattern))
        self.original_if_no_match = original_if_no_match
        self.flags = flags
        self.compiled_pattern = pattern

    def action(self, string_value):
        match = self.compiled_pattern.match(string_value)
        if match is None:
            return string_value if self.original_if_no_match else None
        else:
            return match.group(1)

    def description(self):
        return '{} with pattern: "{}"'.format(type(self).__name__,
                                              self.compiled_pattern.pattern)