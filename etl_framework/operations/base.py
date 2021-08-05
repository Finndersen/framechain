import functools
import logging
import marshal
import operator
import sys
import tempfile
import pprint
from collections import defaultdict
from time import perf_counter, sleep

import pandas as pd

from etl_framework.utils import randomstring

log = logging.getLogger(__name__)


class OperationError(Exception):
    def __init__(self, exc):
        """

        :param exc: Exception to be wrapped
        """
        self.wrapped_exception = exc
        # List of nested operations which define location was raised (raised in first, following are parents)
        self.location = []
        super().__init__()

    def add_location(self, operation):
        self.location.append(operation)

    def __str__(self):
        return 'Exception occurred during operation:\n {}\n{}: {}'.format('\n'.join(str(operation) + ':' for operation
                                                                                    in reversed(self.location)),
                                                                          type(self.wrapped_exception).__name__,
                                                                          str(self.wrapped_exception))


def profiled(method):
    """
    Decorator used to profile an operation method, and add exception handling
    Does not record execution details of profiling already active
    Add this decorator to Operation methods that are not called within action() method
    Makes things easier but adds about 10% extra overhead due to extra function call depending on context...
    :param method:
    :return:
    """

    @functools.wraps(method)
    def profiled_method(self, *args, **kwargs):
        try:
            if self.profiling_enabled and not self.profiling_active:
                self.profiling_active = True
                start_time = perf_counter()
                result = method(self, *args, **kwargs)
                self._call_count += 1
                self._cumulative_time += perf_counter() - start_time
                self.profiling_active = False
            else:
                result = method(self, *args, **kwargs)

            return result
        except Exception as exc:
            # Re-raise exception with operation details if not handled
            if not isinstance(exc, OperationError):
                exc = OperationError(exc).with_traceback(sys.exc_info()[2])

            exc.add_location(self)
            raise exc

    return profiled_method


class OperationOperators(object):
    """
    Implements operator overloading to allow operators to be applied to operation definitions
    The same operator will be applied to the output of each operation when it is called
    Supports:
     - operations to be chained together (output of first goes to input of second) (>>)
     - Perform bitwise operator (vector or scalar) on output of two operations (&, |, ~)
     - Perform arithmetic (vector or scalar) on output of two operations (+, -, *, /)
     - Comparison (>, <, <=, >=, ==)
    """

    # CHAINING
    def __rshift__(self, other):
        return ChainedOperations(self, other)

    # INVERSION
    def __invert__(self):
        return InvertedOperation(self)

    # NEGATE
    def __neg__(self):
        return NegatedOperation(self)

    # CONTAINS/IN
    def __contains__(self, item):
        # IN operator cannot be defferred (coerces output to Bool, so cannot return an IN instance)
        # Use IsIn operation instead
        raise Exception('Use "Contains" operation wrapper instead of "in" operator')

    # SLICING
    def __getitem__(self, item):
        return SlicedOperation(self, item)

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
    """

    def __init__(self):
        self.profiling_enabled = False  # Whether profiling is enabled
        self.profiling_active = False  # Whether profiling is currently active (profiled method is running)
        self._call_count = 0  # Number of times operation has been called
        self._cumulative_time = 0  # Cumulative execution time of operation
        self._wrapped_execution_stats = {}
        self._wrapped_execution_cumtime = 0
        self.wrapped_operations = []
        self._profile_data = None   # Cached profile data
        self.added_profile_data = False   # Whether this operation has added its profile data

    def error(self, exc_type, message):
        """
        Raise error for this operation
        :param exc_type:
        :param message:
        :return:
        """
        raise exc_type('{} operation: {}'.format(type(self).__name__, message))

    def __call__(self, *args, **kwargs):
        try:
            # Re-implement @profiled logic here to avoid overhead of additional function call
            # Otherwise would just do: return profiled(self.action)(*args, **kwargs)
            if self.profiling_enabled and not self.profiling_active:
                start_time = perf_counter()
                self.profiling_active = True
                result = self.action(*args, **kwargs)
                self._call_count += 1
                self.profiling_active = False
                self._cumulative_time += perf_counter() - start_time
                return result
            else:
                return self.action(*args, **kwargs)

        except Exception as exc:
            # Re-raise exception with operation details if not handled
            if not isinstance(exc, OperationError):
                exc = OperationError(exc).with_traceback(sys.exc_info()[2])

            exc.add_location(self)
            raise exc

    def action(self, *args, **kwargs):
        """
        Perform action of operation
        :param args:
        :param kwargs:
        :return:
        """
        raise NotImplementedError()

    def wrap_operation(self, operation, **kwargs):
        """
        Converts operation and adds to list of wrapped operations
        :param operation:
        :param kwargs:
        :return:
        """
        operation = convert_to_operation(operation, **kwargs)
        if operation:
            self.wrapped_operations.append(operation)
        return operation

    def run_wrapped_operation(self, operation, *args, **kwargs):
        """
        Run a wrapped operation and record execution time
        :param Operation operation:
        :param args:
        :param kwargs:
        :return:
        """
        if self.profiling_enabled:
            pre_cum_time = operation.get_cumulative_time()
            pre_tot_time = operation.get_execute_time()
            result = operation(*args, **kwargs)
            delta_cum_time = operation.get_cumulative_time() - pre_cum_time
            delta_tot_time = operation.get_execute_time() - pre_tot_time

            self._wrapped_execution_cumtime += delta_cum_time

            add_profile_stats(self._wrapped_execution_stats, operation.pstat_id, [1, 1, delta_tot_time, delta_cum_time])

            return result
        else:
            return operation(*args, **kwargs)

    def get_wrapped_operation_stats(self, wrapped_operation):
        """
        Get execution stats for wrapped operation for this parent operation
        :param BaseOperation wrapped_operation:
        :return:
        """
        return self._wrapped_execution_stats[wrapped_operation.pstat_id]

    def enable_profiling(self):
        self.clear_profile_stats()
        self.profiling_enabled = True
        for operation in self.wrapped_operations:
            operation.enable_profiling()

    def disable_profiling(self):
        self.profiling_enabled = False
        for operation in self.wrapped_operations:
            operation.disable_profiling()

    def profile_snakeviz(self, input_val):
        """
        Run operation and display profile data with Snakeviz (in Jupyter Notebook)
        :param input_val:
        :return:
        """
        from snakeviz.ipymagic import open_snakeviz_and_display_in_notebook
        self.enable_profiling()
        result = self(input_val)

        profile_data = self.get_profile_data()
        # Get temporary filename
        filename = tempfile.NamedTemporaryFile().name

        with open(filename, 'wb') as f:
            marshal.dump(profile_data, f)

        sv = open_snakeviz_and_display_in_notebook(filename)
        sleep(2)
        sv.terminate()
        self.disable_profiling()
        return result

    def get_profile_data(self):
        if self._profile_data is None:
            profile_data = {}
            self.add_profile_data(profile_data)
            # Verify profile data
            verify_profile_data(profile_data)
            self._profile_data = profile_data
        return self._profile_data

    def add_profile_data(self, profile_data, actual_caller=None, proxy_caller=None):
        """

        :param dict profile_data: Current profile data dictionary
        :param Operation actual_caller: parent calling operation
        :param Operation proxy_caller: Proxy calling operation, can be different to actual_caller if there are
        'transparent' operations in between
        :return:
        """
        self.add_self_profile_data(profile_data, actual_caller, proxy_caller)
        # Add profile data for wrapped operations
        for operation in self.wrapped_operations:
            operation.add_profile_data(profile_data,
                                       actual_caller=self,
                                       proxy_caller=self)

    def add_self_profile_data(self, profile_data, actual_caller, proxy_caller):
        """
        :param dict profile_data: Current profile data dictionary
        :param Operation actual_caller: parent calling operation
        :param Operation proxy_caller: Proxy calling operation, can be different to actual_caller if there are
        'transparent' operations in between
        :return:
        """
        # Dont add to profile stats if not called
        if not self._call_count:
            return

        node_id = self.pstat_id
        node_stats = self.get_execution_stats()

        if not self.added_profile_data:
            add_profile_stats(profile_data, node_id, node_stats + [{}])
            self.added_profile_data = True

        # add profile stats for caller
        if actual_caller:
            stats_for_caller = actual_caller.get_wrapped_operation_stats(self)

            if stats_for_caller[0]:
                # Add to existing caller details
                add_profile_stats(profile_data[node_id][4], proxy_caller.pstat_id, stats_for_caller)

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
        return [self._call_count, self._call_count, self.get_execute_time(), self.get_cumulative_time()]

    def get_cumulative_time(self):
        """
        Get total execution time of this operation (including wrapped sub-operations)
        :return:
        """
        return self._cumulative_time

    def get_execute_time(self):
        """
        Get of just this operation (not including any wrapped sub-operations)
        :return:
        """
        return self.get_cumulative_time() - self._wrapped_execution_cumtime

    @property
    def pstat_id(self):
        """
        Get operation ID for profiling, in format:
        (module_name, line_number, function_name)
        :return:
        """
        desc = self.short_description()
        return (type(self).__name__, id(type(self)), desc)

    def clear_profile_stats(self):
        """
        Reset execution profiling statistics
        :return:
        """
        self.profiling_active = self.added_profile_data = False
        self._cumulative_time = self._call_count = self._wrapped_execution_cumtime = 0
        self._wrapped_execution_stats = {}
        for operation in self.wrapped_operations:
            operation.clear_profile_stats()

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

    def short_description(self):
        """
        Shorter description of operation, useful for simplifying description of compound operations which
        can get unweildy
        :return:
        """
        return self.description()[:180]

    def description(self):
        return type(self).__name__

    def __str__(self):
        return self.description()


def add_profile_stats(container, pstat_id, new_stats):
    """
    Create new stats entry or add to existing
    :param dict container:
    :param tuple pstat_id:
    :param list new_stats: stats in form (call_count, call_count, tottime, cumtime)
    :return:
    """
    if pstat_id in container:
        existing_stats = container[pstat_id]
        for i in range(4):
            existing_stats[i] += new_stats[i]
    else:
        container[pstat_id] = new_stats


class Operation(BaseOperation, OperationOperators):
    """
    Base class for operations which are chainable and support operator overloading
    """
    pass


class OperationsWithOperator(Operation):
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
        super().__init__()
        self.op1 = self.wrap_operation(op1)
        self.op2 = self.wrap_operation(op2)
        # Store operator string
        assert operator_str in self.OPERATORS, '{} is not a valid operator string'.format(operator_str)
        self.operator_str = operator_str

    def action(self, *args, **kwargs):
        # Apply operator on output of two operands
        return self.OPERATORS[self.operator_str](self.run_wrapped_operation(self.op1, *args, **kwargs),
                                                 self.run_wrapped_operation(self.op2, *args, **kwargs))

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


class SingleOperandOperator(Operation):
    """
    Base class for operators which operate on single operand (INVERT, NEG, SLICE)
    Inherits type translations from single contained operation
    """
    operator_str = None

    def __init__(self, op):
        super().__init__()
        self.operation = self.wrap_operation(op)


class InvertedOperation(SingleOperandOperator):
    """Bitwise Invert operator (not for boolean)"""
    operator_str = '~'

    def action(self, *args, **kwargs):
        return ~self.run_wrapped_operation(self.operation, *args, **kwargs)

    def description(self):
        return '~({})'.format(self.operation)


class NegatedOperation(SingleOperandOperator):
    """Invert operator"""
    operator_str = '-'

    def action(self, *args, **kwargs):
        return -self.run_wrapped_operation(self.operation, *args, **kwargs)

    def description(self):
        return '-({})'.format(self.operation)


class SlicedOperation(SingleOperandOperator):
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
        self.key = key
        super().__init__(op)

    def action(self, *args, **kwargs):
        op_result = self.run_wrapped_operation(self.operation, *args, **kwargs)

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


class ChainedOperations(Operation):
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
        super().__init__()
        self.op1 = self.wrap_operation(op1)
        self.op2 = self.wrap_operation(op2)

    def action(self, *args):
        # Return chained output.
        return self.run_wrapped_operation(self.op2, self.run_wrapped_operation(self.op1, *args))

    def add_to_graph(self, graph):
        from pydot import Edge
        start_node1, end_node1 = self.op1.add_to_graph(graph)
        start_node2, end_node2 = self.op2.add_to_graph(graph)
        graph.add_edge(Edge(end_node1, start_node2))
        return start_node1, end_node2

    def add_profile_data(self, profile_data, actual_caller=None, proxy_caller=None):
        """
        Special case where operation chain acts transparently for profile data
        :param dict profile_data:
        :param Operation actual_caller:
        :param Operation proxy_caller:
        :return:
        """
        transparent = isinstance(actual_caller, ChainedOperations)

        # Add profile data for self
        if not transparent:
            self.add_self_profile_data(profile_data, actual_caller, proxy_caller)
        # Add profile data for wrapped operations
        for operation in self.wrapped_operations:
            operation.add_profile_data(profile_data,
                                       actual_caller=self,
                                       proxy_caller=proxy_caller if transparent else self)

    def short_description(self):
        return 'Chain of operations #{}'.format(id(self))

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


class Value(Operation):
    """
    Allows specifying static values (strings, numbers, etc) which can be used in arithmetic or comparison with other operations
    Required when using 'in' operator
    """
    calling_translations = {
        'dataframe': 'value',
        'column': 'value',
        'row': 'value',
        'value': 'value'
    }

    def __init__(self, value):
        super().__init__()
        self.value = value

    def action(self, *args, **kwargs):
        # Return static value regardless of of input
        return self.value

    def description(self):
        return 'Value: "{}"'.format(self.value)


class Lambda(Operation):
    """
    Allows for custom simple transform logic
    Can optionally provide type translation for compatability validation

    """

    def __init__(self, func, description=None, type_translation=None):
        """

        :param func: Callable which takes input value, performs processing logic and returns output
        :param str description: Description of what function does
        :param type_translation: Optionally provide type translation of custom function
        """
        super().__init__()
        self.func = func
        self._description = description or func.__name__
        if type_translation:
            self.calling_translations = type_translation

    def action(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def description(self):
        return self._description


def convert_to_operation(val, none_allowed=False, wrap_value=True):
    """
    Wrap input with appropriate operation if not already an operation
    :param val:
    :param bool none_allowed: Whether operation can be absent
    :param bool wrap_value: Whether to wrap non-callable value in Value Operation
    :return:
    """
    if val is None and none_allowed:
        return None

    if isinstance(val, BaseOperation):
        return val

    if callable(val):
        return Lambda(val)

    if wrap_value:
        return Value(val)
    else:
        raise ValueError('Value is not callable: {}'.format(val))


def verify_profile_data(profile_data):
    """
    Verify PSTAT profile data dictionary
    :param profile_data:
    :return:
    """
    for stat_id, stat_data in profile_data.items():
        caller_data = stat_data[4].values()
        if caller_data:
            # Verify stat data is equal to sum of caller data
            for i in range(4):
                caller_data_sum = sum(cd[i] for cd in caller_data)
                if stat_data[i] != caller_data_sum:
                    raise Exception('Profile data appears to be incorrect for {}:\n{}\n{} != {}'.format(stat_id,
                                                                                                        pprint.pformat(stat_data),
                                                                                                        stat_data[i],
                                                                                                        caller_data_sum))
