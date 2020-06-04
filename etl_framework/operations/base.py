from etl_framework.exceptions import ETLConfigurationError, UnsupportedOperatorError
from etl_framework.utils import validate_callable
import pandas as pd
import operator, logging
log = logging.getLogger(__name__)


class TypeTranslations(object):
    """
    Class which holds base configurations and helper methods relating to type translations
    """
    TYPE_HIERARCHY = {
        'dataframe': 3,
        'column': 2,
        'row': 2,
        'value': 1
    }

    # Generic type translation and compatability
    GENERIC_TYPE_TRANSLATIONS = {
        'dataframe': 'dataframe',
        'row': 'row',
        'column': 'column',
        'value': 'value',
    }

    @classmethod
    def get_for_operation(cls, operation):
        """
        Get defined calling type translations of operation, or generic defaults if not specified
        :param operation:
        :return:
        """
        return getattr(operation, 'calling_translations', cls.GENERIC_TYPE_TRANSLATIONS)

    @staticmethod
    def check_operator_allowed(operation, operator_str):
        """
        Checks whether the provided operation is compatible with operators (must return column or value type)
        :param operation:
        :return:
        """
        output_types = set(getattr(operation, 'calling_translations', {'placeholder': 'column'}).values())
        if not output_types.intersection({'column', 'value'}):
            raise UnsupportedOperatorError('Operation: {} does not support operator: {}'.format(operation, operator_str))


class BaseOperation(object):
    """
    Base operation class. An operation is anything that performs some kind of action in the ETL pipeline
    Implements operator overloading to allow operators to be applied to operation definitions
    The same operator will be applied to the output of each operation when it is called
    Supports:
     - operations to be chained together (output of first goes to input of second) (>>)
     - Perform bitwise operator (vector or scalar) on output of two operations (&, |, ~)
     - Perform arithmetic (vector or scalar) on output of two operations (+, -, *, /)
     - Comparison (>, <, <=, >=, ==)

    """
    # Mapping of valid input types to valid output types (for when this class is called)
    calling_translations = {}

    def __call__(self, *args, **kwargs):
        raise NotImplementedError()

    def __str__(self):
        return type(self).__name__

    # CHAINING
    def __rshift__(self, other):
        # if other is None:
        #     return self
        # else:
        return THEN(self, other)

    # INVERSION
    def __invert__(self):
        return INVERT(self)

    # NEGATE
    def __neg__(self):
        return NEG(self)

    # CONTAINS/IN
    def __contains__(self, item):
        # IN operator cannot be defferred (coerces output to Bool, so cannot return an IN instance)
        # Use IsIn operation instead
        raise Exception('Use "Contains" operation wrapper instead of "in" operator')

    # SLICING
    def __getitem__(self, item):
        return SLICE(self, item)

    # BITWISE
    def __and__(self, other):
        return OperationsWithOperator(self, other, '&')

    def __rand__(self, other):
        return OperationsWithOperator(other, self, '&')

    def __or__(self, other):
        return OperationsWithOperator(self, other, '|')

    def __ror__(self, other):
        return OperationsWithOperator(other, self, '|')

    # ARITHMETIC
    def __add__(self, other):
        return OperationsWithOperator(self, other, '+')

    def __radd__(self, other):
        return OperationsWithOperator(other, self, '+')

    def __mul__(self, other):
        return OperationsWithOperator(self, other, '*')

    def __rmul__(self, other):
        return OperationsWithOperator(other, self, '*')

    def __pow__(self, other):
        return OperationsWithOperator(self, other, '**')

    def __rpow__(self, other):
        return OperationsWithOperator(other, self, '**')

    def __sub__(self, other):
        return OperationsWithOperator(self, other, '-')

    def __rsub__(self, other):
        return OperationsWithOperator(other, self, '-')

    def __truediv__(self, other):
        return OperationsWithOperator(self, other, '/')

    def __rtruediv__(self, other):
        return OperationsWithOperator(other, self, '/')

    def __floordiv__(self, other):
        return OperationsWithOperator(self, other, '//')

    def __rfloordiv__(self, other):
        return OperationsWithOperator(other, self, '//')

    def __mod__(self, other):
        return OperationsWithOperator(self, other, '%')

    def __rmod__(self, other):
        return OperationsWithOperator(other, self, '%')

    # COMPARISON
    def __gt__(self, other):
        return OperationsWithOperator(self, other, '>')

    def __ge__(self, other):
        return OperationsWithOperator(self, other, '>=')

    def __eq__(self, other):
        return OperationsWithOperator(self, other, '==')

    def __lt__(self, other):
        return OperationsWithOperator(self, other, '<')

    def __le__(self, other):
        return OperationsWithOperator(self, other, '<=')

    def __ne__(self, other):
        return OperationsWithOperator(self, other, '!=')


class OperationsWithOperator(BaseOperation):
    """
    Class used to define an operator (e.g. AND, OR, ADD, MINUS, MULTIPLY),
    and the operands to operate on (generally operations/activities)
    Inherit highest-dimension output types from stored operations (arithmetic with vector and scalar will produce vector)
    """
    OPERATORS = {
        '&': operator.and_,
        '|': operator.or_,
        '*': operator.mul,
        '**': operator.pow,
        '+': operator.add,
        '-': operator.sub,
        '/': operator.truediv,
        '//': operator.floordiv,
        '%': operator.mod,
        '>': operator.gt,
        '>=': operator.ge,
        '==': operator.eq,
        '<': operator.lt,
        '<=': operator.le,
        '!=': operator.ne
    }

    def __init__(self, op1, op2, operator_str):
        """

        :param op1: First (left side) operation
        :param op2: Second (right side) operation
        :param str operator_str: String representing operator
        """
        # Store operands
        self.op1 = validate_callable(op1)
        self.op2 = validate_callable(op2)
        # Store operator string
        assert operator_str in self.OPERATORS, '{} is not a valid operator string'.format(operator_str)
        self.operator_str = operator_str
        # Validate operation input types (both must have common valid input type)
        op1_translations = TypeTranslations.get_for_operation(op1)
        op2_translations = TypeTranslations.get_for_operation(op2)
        # Check if operations are compatible with operators
        for op in [op1, op2]:
            TypeTranslations.check_operator_allowed(op, operator_str)
        # Verify operations both have a shared input type
        valid_inputs = set(op1_translations).intersection(set(op2_translations))
        if not valid_inputs:
            raise ETLConfigurationError('({}) and ({}) cannot be operated together because they do not share a common valid input type'.format(op1, op2))

        # Use highest-hierarchy outputs (operating on scalar and vector will produce vector)
        self.calling_translations = {in_type: max([op1_translations[in_type], op2_translations[in_type]],
                                                  key=lambda out_type: TypeTranslations.TYPE_HIERARCHY[out_type])
                                     for in_type in valid_inputs}

    def __call__(self, *args, **kwargs):
        # Apply operator on output of two operands
        return self.OPERATORS[self.operator_str](self.op1(*args, **kwargs), self.op2(*args, **kwargs))

    def __str__(self):
        return '({}) {} ({})'.format(self.op1, self.operator_str, self.op2)

    def _op_repr(self, op):
        """
        Get string representation for operation or scalar value
        :param op:
        :return:
        """
        if isinstance(op, BaseOperation):
            return '({})'.format(op)
        elif isinstance(op, str):
            return '"{}"'.format(op)
        else:
            return str(op)


class SingleOperandOperator(BaseOperation):
    """
    Base class for operators which operate on single operand (NOT, IN, SLICE)
    Inherits type translations from single contained operation
    """
    operator_str = None

    def __init__(self, op):
        TypeTranslations.check_operator_allowed(op, self.operator_str)
        self.op = op
        # Inherit type translations
        self.calling_translations = TypeTranslations.get_for_operation(op)


class INVERT(SingleOperandOperator):
    """Invert operator"""
    operator_str = '~'

    def __call__(self,*args, **kwargs):
        return ~self.op(*args, **kwargs)

    def __str__(self):
        return '~({})'.format(self.op)


class NEG(SingleOperandOperator):
    """Invert operator"""
    operator_str = '-'

    def __call__(self,*args, **kwargs):
        return -self.op(*args, **kwargs)

    def __str__(self):
        return '-({})'.format(self.op)


class SLICE(SingleOperandOperator):
    """
    Enables string slicing of operator return value
    Can do vectorised pd.str.slice, or standard string slicing on scalar values
    """
    operator_str = '[]'

    def __init__(self, op, key):
        """

        :param op: Operation being sliced
        :param key: Slice or indexing key
        """
        if not isinstance(key, (slice, int)):
            raise ETLConfigurationError('Indexing key must be integer or slice')
        self.key=key
        # Attempt to determine operation output type
        op_type_translation = TypeTranslations.get_for_operation(op)
        if len(op_type_translation) == 1:
            self.result_type = op_type_translation.values()[0]
        else:
            self.result_type = None
        super().__init__(op)

    def __call__(self, *args, **kwargs):
        op_result = self.op(*args, **kwargs)

        if self.result_type == 'column':
            # Pandas vectorised string slice
            return op_result.str[self.key]
        elif self.result_type == 'value':
            # Standard string slice
            return op_result[self.key]
        else:
            # Unknown result type, Check if result is Series or scalar value
            if isinstance(op_result, pd.Series):
                return op_result.str[self.key]
            else:
                return op_result[self.key]

    def __str__(self):
        if isinstance(self.key, slice):
            if self.key.step:
                slice_str = '[{}:{}:{}]'.format(self.key.start or '', self.key.stop or '', self.key.step)
            else:
                slice_str = '[{}:{}]'.format(self.key.start or '', self.key.stop or '')
        else:
            slice_str = '[{}]'.format(self.key)
        return '({}){}'.format(self.op, slice_str)


class THEN(BaseOperation):
    """
    Holds operators to be chained together
    Also contains validation logic for checking compatability of chained operations
    (output types of op1 must be in op2 input types)
    """
    def __init__(self, op1, op2):
        chained_translations = self.get_chained_calling_translations(op1, op2)
        # Two operations are not compatible for chaining
        if not chained_translations:
            raise ETLConfigurationError('{} is not compatible to be chained with: {}'.format(op1, op2))
        self.calling_translations = chained_translations
        # Store operations
        self.op1 = op1
        self.op2 = op2

    def __call__(self, val):
        # Return chained output.
        return self.op2(self.op1(val))

    def get_chained_calling_translations(self, op1, op2):
        """
        Get chained type translation across two operations
        If translations are not specified, assume operation has full compatability and does no translation
        :param op1: operation whos input will be provided by this wrapping class
        :param op2: operation whos input will be provided by op1
        :return:
        """
        op1_translations = TypeTranslations.get_for_operation(op1)
        op2_translations = TypeTranslations.get_for_operation(op2)
        # Build chained translation
        chained_translations = {op1_in: op2_translations[op1_out]
                                for op1_in, op1_out in op1_translations.items()
                                if op1_out in op2_translations}
        return chained_translations

    def __str__(self):
        return '({}) -> ({})'.format(self.op1, self.op2)


class DataframeOperation(BaseOperation):
    """
    Base class for operations that take entire dataframe and return single Series
    """
    calling_translations = {'dataframe': 'column'}

    def __call__(self, dataframe):
        """
        Take dataframe and return series
        :return: boolen series
        """
        raise NotImplementedError()


class ColumnOperation(BaseOperation):
    """
    Base Class for operations that operate on one or more columns to perform vectorised condition logic and return single Series
    Could be transforms, conditionals or converters
    Use 'SelectField' operation or 'OnField' or 'MapFields' wrappers to supply individual column(s) from dataframe
    """
    calling_translations = {'column': 'column'}

    # Whether the operation can change the DTYPE of the column. Used by ConvertField to decide whether to apply condition
    changes_type = False

    def __call__(self, *args, **kwargs):
        """
        Take one or more columns or scalar values
        :return: series
        """
        raise NotImplementedError()


class ScalarOperation(BaseOperation):
    """
    Operation that uses scalar logic to operate on one or more row values (when vectorisation is not possible)
    Use Apply wrapper to step-down vector (Dataframe or Series) to Scalar (Row or value)

    """
    calling_translations = {'value': 'value'}

    def __call__(self, *args, **kwargs):
        """

        :param args:
        :param kwargs:
        :return:
        """
        raise NotImplementedError()


class ScalarOrVectorOperation(BaseOperation):
    """
    Operation which can take either scalar or vector input values
    Should specify which type is expected when initialised
    Behaviour can be adjusted depending on specified input type
    """
    calling_translations = {
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, input_type='column'):
        # Filter type translations
        if input_type not in self.calling_translations:
            raise ETLConfigurationError('Input type "{}" is invalid for {}'.format(input_type, type(self).__name__))
        self.calling_translations = {input_type: self.calling_translations[input_type]}
        self.input_type = input_type


class WrappingTypeTranslatorMixin(object):
    """
    Mixin to help validate compatability of operation supplied to wrapper
    Output types of mapper must align with input types of mapped operation
    """
    # Translations of input calling types to types passed to wrapped operation
    wrapping_translations = {}

    def validate_wrapped_operation_compatability(self, wrapped_operation):
        """
        Get chained type translation across two operations, with optional input types
        If translations are not specified, assume operation has full compatability and does no translation
        :param wrapped_operation: operation whos input will be provided by this wrapping class
        :return:
        """
        wrapped_valid_translations = TypeTranslations.get_for_operation(wrapped_operation)
        # Wrapping translations which are compatible with wrapped operation
        valid_wrapping_translations = {wrapping_in: wrapped_valid_translations[wrapping_out]
                                for wrapping_in, wrapping_out in self.wrapping_translations.items()
                                if wrapping_out in wrapped_valid_translations}
        if  valid_wrapping_translations:
            # Filter valid translations using valid wrapping translations
            self.calling_translations={key: val
                                       for key,val in TypeTranslations.get_for_operation(self).items()
                                       if key in valid_wrapping_translations}
        else:
            # Transform/wrapper not compatible with this wrapper
            raise ETLConfigurationError(
                '{} is not compatible with wrapper: {}'.format(type(wrapped_operation).__name__, type(self).__name__))
