from etl_framework.operations import Operation
import re


class RegexExtract(Operation):
    """
    Extract value from string using regex pattern with asingle capture group
    """
    def __init__(self, pattern, **flags):
        """

        :param str or re.pattern pattern: Regex pattern to match on
        :param flags: Extra flags for regex library
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        # Validate pattern has only one capture group
        if pattern.groups != 1:
            raise ValueError('Regex pattern: "{}" should have only one capture group'.format(pattern.pattern))

        self.flags = flags
        self.compiled_pattern = pattern

    def action(self, string_value):
        match = self.compiled_pattern.match(string_value)
        if match is None:
            return None
        else:
            return match.group(1)

    def description(self):
        return 'RegexExtract with pattern: "{}"'.format(self.compiled_pattern.pattern)