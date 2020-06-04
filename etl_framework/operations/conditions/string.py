from etl_framework.operations.base import ColumnOperation, ScalarOrVectorOperation
import re

class Contains(ScalarOrVectorOperation):
    """
    Test whether string column values contain pattern or regex
    """
    def __init__(self, pattern, regex=False, input_type='column'):
        """

        :param str pattern: search pattern
        :param bool regex: Whether pattern is regex
        """
        self.pattern = re.compile(pattern) if regex else pattern
        self.regex = regex
        super().__init__(input_type)

    def __call__(self, value):
        if self.input_type == 'column':
            return value.str.contains(self.pattern, regex=self.regex)
        elif self.regex:
            return self.pattern.search(value)
        else:
            return self.pattern in value


class IsNumeric(ScalarOrVectorOperation):
    """
    Test whether string values are numeric
    """
    def __call__(self, value):
        if self.input_type == 'column':
            return value.str.isnumeric()
        else:
            return value.isnumeric()