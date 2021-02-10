from etl_framework.operations.types import TypeTranslations
from etl_framework.utils import validate_callable, randomstring
import pandas as pd
import sys
import operator, logging, time, marshal

log = logging.getLogger(__name__)


class OperationError(Exception):
    def __init__(self, operation, exc):
        message = 'Exception occured during operation: {}\n{}: {}'.format(operation, type(exc).__name__, str(exc))
        super().__init__(message)


class OperationOperators(object):
    """
    Mixin to add operator overloading to allow operator chaining and numeric / binary / comparison operators
    """

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
    # calling_translations = None
    call_count = 0
    _culumative_time = 0

    def error(self, exc_type, message):
        """
        Raise error for this operation
        :param exc_type:
        :param message:
        :return:
        """
        raise exc_type('{} operation: {}'.format(type(self).__name__, message))

    def __call__(self, *args, **kwargs):
        # Record execution time, etc..
        try:
            start_time = time.perf_counter()
            result = self.action(*args, **kwargs)
            self.call_count += 1
            self._culumative_time += time.perf_counter() - start_time
            return result
        except Exception as exc:
            exc_result = self.handle_exception(exc, *args, **kwargs)
            # Re-raise exception with operation details if not handled
            if exc_result is None:
                if isinstance(exc, OperationError):
                    raise
                else:
                    raise OperationError(self, exc).with_traceback(sys.exc_info()[2])
            else:
                return exc_result

    def action(self, *args, **kwargs):
        """
        Perform action of operation
        :param args:
        :param kwargs:
        :return:
        """
        raise NotImplementedError()

    def profile_snakeviz(self, input_val):
        """
        Run operation and display profile data with Snakeviz (in Jupyter Notebook)
        :param input_val:
        :return:
        """
        from snakeviz.ipymagic import open_snakeviz_and_display_in_notebook
        self.clear_profile_stats()
        result = self(input_val)

        profile_data = self.get_profile_data()
        with open('pstat_data', 'wb') as f:
            marshal.dump(profile_data, f)

        sv = open_snakeviz_and_display_in_notebook('pstat_data')
        time.sleep(2)
        sv.terminate()
        return result

    def get_profile_data(self):
        profile_data = {}
        self.add_profile_data(profile_data)
        return profile_data

    def add_profile_data(self, profile_data, caller=None, add_self_data=True):
        if add_self_data:
            node_id = self.pstat_id
            node_stats = self.get_execution_stats()
            # Dont add to profile stats if it is not called
            if not node_stats[0]:
                return

            if node_id in profile_data:
                # Add to existing profile data for this operation (can be multiple instances of same operation)
                if caller:
                    profile_data[node_id][4][caller.pstat_id] = caller.get_execution_stats()
                for i in range(4):
                    profile_data[node_id][i] += node_stats[i]
            else:
                # Create new entry
                caller_dict = {caller.pstat_id: caller.get_execution_stats()} if caller else {}
                profile_data[node_id] = node_stats + [caller_dict]

        return profile_data

    def get_execution_stats(self):
        """
        Get execution stats for use in profiling. List with elements:
        [0] = The number of times this function was called, not counting direct or indirect recursion,
        [1] = Number of times this function appears on the stack, minus one
        [2] = Total time spent internal to this function
        [3] = Cumulative time that this function was present on the stack.  In
              non-recursive functions, this is the total execution time from start
              to finish of each invocation of a function, including time spent in
              all subfunctions.

        :return:
        """
        return [self.call_count, self.call_count, self.get_execute_time(), self.get_culumative_time()]

    def get_culumative_time(self):
        """
        Get total execution time of this operation (including wrapped sub-operations)
        :return:
        """
        return self._culumative_time

    def get_execute_time(self):
        """
        Get of just this operation (not including any wrapped sub-operations)
        :return:
        """
        return self._culumative_time

    @property
    def pstat_id(self):
        """
        Get operation ID for profiling, in format:
        (module_name, line_number, function_name)
        :return:
        """
        desc = self.description()
        if len(desc) > 180:
            desc = self.short_description()
        return ('', id(self), desc)

    def clear_profile_stats(self):
        self._culumative_time = 0
        self.call_count = 0

    def show_graph(self):
        from pydot import Dot
        from IPython.display import Image, display
        graph = Dot(graph_name="G", compound='true', graph_type='digraph')
        start_node, end_node = self.add_to_graph(graph)
        plt = Image(graph.create(format='png'))
        display(plt)

    def add_to_graph(self, graph):
        """
        Add operation as node(s) to graph
        Return start and end node added (can be multiple nodes for compound operations)
        :param graph:
        :return:
        """
        from pydot import Node
        # Use random string as node name (so each operation is unique)
        node = Node(name=randomstring(10), label=self.short_description())
        graph.add_node(node)
        return node, node

    def handle_exception(self, exc, *args, **kawrgs):
        """
        Handle exception raised during action().
        Allows 'ask forgiveness not permission' style implementation in action() for greater performance
        Can be used to provide more meaningful context-specific error messages, or logging
        Any non-None return value will be used as operation return value
        :param exc:
        :return:
        """
        pass

    def short_description(self):
        """
        Shorter description of operation, useful for simplifying description of compound operations which
        can get unweildy
        :return:
        """
        return self.description()

    def description(self):
        return type(self).__name__

    def __str__(self):
        return self.description()


class Operation(BaseOperation, OperationOperators):
    """
    Base class for operations which are chainable and support operator overloading
    """
    pass


class OperatorWrapperMixin(BaseOperation):
    """
    Mixin for operations which wrap other operations
    Handles profiling of wrapped operations
    """
    def __init__(self, *wrapped_operations):
        """

        :param Operation wrapped_operations: operations which are encapsulated within (called by) this one
        """
        self.wrapped_operations = wrapped_operations

    def add_profile_data(self, profile_data, caller=None, add_self_data=True):
        """

        :param profile_data:
        :param caller:
        :param bool add_self_data: Whether this operation wrapper should include its own profile stats, or be
        'transparent'
        :return:
        """
        profile_data = super().add_profile_data(profile_data, caller=caller, add_self_data=add_self_data)
        for operation in self.wrapped_operations:
            profile_data = operation.add_profile_data(profile_data, self if add_self_data else caller)
        return profile_data

    def get_execute_time(self):
        tottime = self.get_culumative_time()
        for operation in self.wrapped_operations:
            tottime -= operation.get_culumative_time()
        return tottime

    def clear_profile_stats(self):
        super().clear_profile_stats()
        for operation in self.wrapped_operations:
            operation.clear_profile_stats()


class CompoundOperation(OperatorWrapperMixin, Operation):
    """
    Base class for operations which wrap or contain other operations.
    Used to propogate method calls such as profiling down to encapsulated operations
    """
    pass


class OperationsWithOperator(CompoundOperation):
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
        self.op1 = validate_callable(op1)
        self.op2 = validate_callable(op2)
        # Store operator string
        assert operator_str in self.OPERATORS, '{} is not a valid operator string'.format(operator_str)
        self.operator_str = operator_str
        super().__init__(self.op1, self.op2)
        # Validate operation input types (both must have common valid input type)
        # TODO: Rework operation type compatability
        # op1_translations = TypeTranslations.get_for_operation(op1)
        # op2_translations = TypeTranslations.get_for_operation(op2)
        # # Check if operations are compatible with operators
        # for op in [op1, op2]:
        #     TypeTranslations.check_operator_allowed(op, operator_str)
        # # Verify operations both have a shared input type
        # valid_inputs = set(op1_translations).intersection(set(op2_translations))
        # if not valid_inputs:
        #     raise ETLConfigurationError('({}) and ({}) cannot be operated together because they do not share a common valid input type'.format(op1, op2))
        #
        # # Use highest-hierarchy outputs (operating on scalar and vector will produce vector)
        # self.calling_translations = {in_type: max([op1_translations[in_type], op2_translations[in_type]],
        #                                           key=lambda out_type: TypeTranslations.TYPE_HIERARCHY[out_type])
        #                              for in_type in valid_inputs}

    def action(self, *args, **kwargs):
        # Apply operator on output of two operands
        return self.OPERATORS[self.operator_str](self.op1(*args, **kwargs), self.op2(*args, **kwargs))

    def description(self):
        return '({}) {} ({})'.format(self.op1, self.operator_str, self.op2)

    def _op_repr(self, op):
        """
        Get string representation for operation or scalar value
        :param op:
        :return:
        """
        if isinstance(op, Operation):
            return '({})'.format(op)
        elif isinstance(op, str):
            return '"{}"'.format(op)
        else:
            return str(op)


class SingleOperandOperator(CompoundOperation):
    """
    Base class for operators which operate on single operand (NOT, IN, SLICE)
    Inherits type translations from single contained operation
    """
    operator_str = None

    def __init__(self, op):
        TypeTranslations.check_operator_allowed(op, self.operator_str)
        self.operation = op
        # Inherit type translations
        # self.calling_translations = TypeTranslations.get_for_operation(op)
        super().__init__(self.operation)


class INVERT(SingleOperandOperator):
    """Invert operator"""
    operator_str = '~'

    def action(self, *args, **kwargs):
        return ~self.operation(*args, **kwargs)

    def description(self):
        return '~({})'.format(self.operation)


class NEG(SingleOperandOperator):
    """Invert operator"""
    operator_str = '-'

    def action(self, *args, **kwargs):
        return -self.operation(*args, **kwargs)

    def description(self):
        return '-({})'.format(self.operation)


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
            self.error(ValueError, 'Indexing key must be integer or slice')
        self.key=key
        # Attempt to determine operation output type
        op_type_translation = TypeTranslations.get_for_operation(op)
        if len(op_type_translation) == 1:
            self.result_type = list(op_type_translation.values())[0]
        else:
            self.result_type = None
        super().__init__(op)

    def action(self, *args, **kwargs):
        op_result = self.operation(*args, **kwargs)

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

    def description(self):
        if isinstance(self.key, slice):
            if self.key.step:
                slice_str = '[{}:{}:{}]'.format(self.key.start or '', self.key.stop or '', self.key.step)
            else:
                slice_str = '[{}:{}]'.format(self.key.start or '', self.key.stop or '')
        else:
            slice_str = '[{}]'.format(self.key)
        return '({}){}'.format(self.operation, slice_str)


class THEN(CompoundOperation):
    """
    Holds operators to be chained together
    Also contains validation logic for checking compatability of chained operations
    (output types of op1 must be in op2 input types)
    """
    def __init__(self, op1, op2):
        """

        :param op1: First (left side) operation
        :param op2: Second (right side) operation
        """
        self.op1 = validate_callable(op1)
        self.op2 = validate_callable(op2)
        super().__init__([self.op1, self.op2])

    def action(self, *args):
        # Return chained output.
        return self.op2(self.op1(*args))

    def add_to_graph(self, graph):
        from pydot import Edge
        start_node1, end_node1 = self.op1.add_to_graph(graph)
        start_node2, end_node2 = self.op2.add_to_graph(graph)
        graph.add_edge(Edge(end_node1, start_node2))
        return start_node1, end_node2

    def add_profile_data(self, profile_data, caller=None, add_self_data=False):
        return super().add_profile_data(profile_data,
                                        caller=caller,
                                        # Add root-level caller if none provided
                                        add_self_data=add_self_data or caller is None)

    def short_description(self):
        return 'Long chain of operations'

    def description(self):
        return '({}) --> ({})'.format(self.op1, self.op2)


class UnchainableOperation(object):
    """
    Mixin which disables chaining (operator overload) capability of operation
    """
    # CHAINING
    __rshift__ = property()
    # INVERSION
    __invert__ = property()

    # NEGATE
    __neg__ = property()

    # CONTAINS/IN
    __contains__ = property()

    # SLICING
    __getitem__ = property()

    # BITWISE
    __and__ = property()

    __rand__ = property()

    __or__ = property()

    __ror__ = property()

    # ARITHMETIC
    __add__ = property()

    __radd__ = property()

    __mul__ = property()

    __rmul__ = property()

    __pow__ = property()

    __rpow__ = property()

    __sub__ = property()

    __rsub__ = property()

    __truediv__ = property()

    __rtruediv__ = property()

    __floordiv__ = property()

    __rfloordiv__ = property()

    __mod__ = property()

    __rmod__ = property()

    # COMPARISON
    __gt__ = property()

    __ge__ = property()

    __eq__ = property()

    __lt__ = property()

    __le__ = property()

    __ne__ = property()


class UncallableOperation(object):
    """
    Mixin to make operation not callable
    """
    __call__ = property()


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
        # Temporarily disabled. TODO: FIX
        # wrapped_valid_translations = TypeTranslations.get_for_operation(wrapped_operation)
        # # Wrapping translations which are compatible with wrapped operation
        # valid_wrapping_translations = {wrapping_in: wrapped_valid_translations[wrapping_out]
        #                         for wrapping_in, wrapping_out in self.wrapping_translations.items()
        #                         if wrapping_out in wrapped_valid_translations}
        # if  valid_wrapping_translations:
        #     # Filter valid translations using valid wrapping translations
        #     self.calling_translations={key: val
        #                                for key,val in TypeTranslations.get_for_operation(self).items()
        #                                if key in valid_wrapping_translations}
        # else:
        #     # Transform/wrapper not compatible with this wrapper
        #     raise ETLConfigurationError(
        #         '{} is not compatible with wrapper: {}'.format(type(wrapped_operation).__name__, type(self).__name__))
