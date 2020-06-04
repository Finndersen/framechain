from etl_framework.operations import NoOp
from etl_framework.operations.base import ColumnOperation, BaseOperation


class ValueIn(ColumnOperation):
    """
    Condition to select rows with column values in specified collection
    Input: Series
    Output: Boolean Series
    e.g.
    ValueIn(['red', 'brown', 'blonde'])

    """

    def __init__(self, values):
        """

        :param list/tuple/set values: Values to match on
        """
        self.equate_values = values

    def __call__(self, column):
        return column.isin(self.equate_values)

    def __str__(self):
        return ' values in {}'.format(self.equate_values)


class IsNull(ColumnOperation):
    """
    Select rows which are NA (None or np.NaN)
    """

    def __call__(self, column):
        return column.isna()

    def __str__(self):
        return ' is Null'


class If(BaseOperation):
    """
    Conditional statement to choose between executing one or another operation
    """
    calling_translations = {
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, condition, true_operation, false_operation=NoOp()):
        """

        :param condition: Callable which takes input and returns True or False
        :param true_operation: Operation to execute if condition returns True
        :param false_operation: Operation to execute if condition returns False (defaults to no action)
        """
        self.false_operation = false_operation
        self.true_operation = true_operation
        self.condition = condition

    def __call__(self, value):
        if self.condition(value):
            return self.true_operation(value)
        else:
            return self.false_operation(value)

    def __str__(self):
        return 'If {} then ({}), else ({})'.format(self.condition.__name__, self.true_operation, self.false_operation)