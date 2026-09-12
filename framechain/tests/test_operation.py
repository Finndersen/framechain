import operator
from unittest import TestCase

from framechain.operations import Pass, Value, Operation


class AddValue(Operation):
    """
    Simple operation for testing
    """
    def __init__(self, value):
        super().__init__()
        self.value = value

    def action(self, arg):
        return arg + self.value


class OperationTests(TestCase):
    """
    Test core Operation functionality
    """
    def test_chaining(self):
        """
        Test operation chaining (ChainedOperations funcitonality)
        :return:
        """
        # Test simple chaining
        add5 = AddValue(5)
        add10 = AddValue(10)
        add15_to_str = add5 >> add10 >> str
        self.assertEqual(add15_to_str(1), '16')

        # Test length
        self.assertEqual(len(add15_to_str), 3)

        # Test chaining with Pass or None
        self.assertEqual(len(add15_to_str >> Pass()), 3)
        self.assertEqual(len(add15_to_str >> None), 3)

        # Test indexing
        self.assertIs(add15_to_str[0], add5)

        # Test slicing
        self.assertEqual(add15_to_str[0:2].child_operations, [add5, add10])
        self.assertEqual(add15_to_str[1:2], add10)

        # Test iteration
        for operation in add15_to_str:
            self.assertIsInstance(operation, Operation)

    def test_binary_operators(self):
        """
        Test operators which involve 2 values (OperationsWithOperator functionality)
        :return:
        """
        OPERATORS = [
            operator.and_,
            operator.or_,
            operator.mul,
            operator.pow,
            operator.add,
            operator.sub,
            operator.truediv,
            operator.floordiv,
            operator.mod,
            operator.gt,
            operator.ge,
            operator.eq,
            operator.lt,
            operator.le,
            operator.ne
        ]
        for op in OPERATORS:
            # Same value
            self.assertEqual(op(Pass(), Pass())(5), op(5, 5))
            # Automatic value conversion
            self.assertEqual(op(Value(12), 5)(), op(12, 5))
            # Automatic callable conversion
            self.assertEqual(op(Pass(), lambda x: x*2)(5), op(5, 5*2))

    def test_negate(self):
        """
        :return:
        """
        self.assertEqual((-Pass())(5), -5)
        self.assertEqual((-Value(10))(), -10)

    def test_invert(self):
        """
        Test InvertedOperation functionality
        :return:
        """
        self.assertEqual((~Pass())(5), ~5)
        self.assertEqual((~Value(10))(), ~10)

    def test_slice(self):
        """
        Test SlicedOperation functionality
        :return:
        """
        self.assertEqual((Pass()[1:3])('hello'), 'el')

