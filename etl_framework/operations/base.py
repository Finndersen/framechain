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

from etl_framework.exceptions import InvalidProfileDataError
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
        return 'Exception occurred during operation:\n{}\n{}: {}'.format('\n'.join(operation.description() + ':' for operation
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
    def profiled_method(self, *args):
        try:
            # Profiling may already be active if called from another @profiled method
            if self.profiling_enabled and not self.profiling_active:
                start_time = perf_counter()
                # Get profile stats of child operations before running
                before_child_profile_stats = {
                    id(operation): operation.get_execution_stats() for operation in self.child_operations
                }
                before_child_overhead_time = sum(child.get_total_overhead_time() for child in self.child_operations)
                self.profiling_active = True

                # Run operation
                before_run_time = perf_counter()
                result = method(self, *args)
                after_run_time = perf_counter()

                # Get change in child operation profile stats associated with this parent operation
                for operation in self.child_operations:
                    child_stat_delta = get_stat_delta(before_child_profile_stats[id(operation)],
                                                      operation.get_execution_stats())

                    add_profile_stats(self._child_execution_stats,
                                      id(operation),
                                      child_stat_delta,
                                      primary=False)

                # Update profile timings
                child_overhead_delta = (sum(child.get_total_overhead_time() for child in self.child_operations)
                                        - before_child_overhead_time)
                # Update total execution time (including child operation time) excluding overhead time
                self._cumulative_time += (after_run_time - before_run_time - child_overhead_delta)
                self._call_count += 1
                self.profiling_active = False
                self._overhead_time += (perf_counter() - after_run_time) + (before_run_time - start_time)
                return result
            else:
                return method(self, *args)

        except Exception as exc:
            # Re-raise exception with operation details if not handled
            if not isinstance(exc, OperationError):
                exc = OperationError(exc).with_traceback(sys.exc_info()[2])

            exc.add_location(self)
            raise exc

    return profiled_method


class BaseOperation(object):
    """
    Base operation class. An operation is anything that contains logic for processing an input and producing an output
    Includes support for:
    - Execution profiling
    - Containing child operations and cascading methods to them
    - creating visual graphs
    """

    def __init__(self):
        self.child_operations = []  # List of child operations

        self.profiling_enabled = False  # Whether profiling is enabled
        self.profiling_active = False  # Whether profiling is currently active (profiled method is running)
        self._call_count = 0  # Number of times operation has been called
        # Cumulative execution time of operation and child operations (excluding overhead time of child operations)
        self._cumulative_time = 0
        self._overhead_time = 0     # Time consumed recording profile stats for this operation
        self._child_execution_stats = {}    # Mapping of child operation IDs to profile stats for this parent

    def error(self, exc_type, message):
        """
        Raise error for this operation
        :param exc_type:
        :param message:
        :return:
        """
        raise exc_type('{} operation: {}'.format(type(self).__name__, message))

    def __call__(self, *args):
        try:
            # Re-implement @profiled logic here to avoid overhead of additional function call
            # Otherwise would just do: return profiled(self.action)(*args,)
            # Profiling may already be active if called from another @profiled method
            if self.profiling_enabled and not self.profiling_active:
                start_time = perf_counter()
                # Get profile stats of child operations before running
                before_child_profile_stats = {
                    id(operation): operation.get_execution_stats() for operation in self.child_operations
                }
                before_overhead_time = self.get_total_overhead_time()
                self.profiling_active = True

                # Run operation
                before_run_time = perf_counter()
                result = self.action(*args)
                after_run_time = perf_counter()

                # Get change in child operation profile stats associated with this parent operation
                for operation in self.child_operations:
                    child_stat_delta = get_stat_delta(before_child_profile_stats[id(operation)],
                                                     operation.get_execution_stats())

                    add_profile_stats(self._child_execution_stats,
                                      id(operation),
                                      child_stat_delta,
                                      primary=False)
                # Update profile timings
                child_overhead_delta = self.get_total_overhead_time() - before_overhead_time
                # Update total execution time (excluding child overhead time)
                self._cumulative_time += (after_run_time - before_run_time - child_overhead_delta)
                self._call_count += 1
                self.profiling_active = False
                self._overhead_time += (perf_counter() - after_run_time) + (before_run_time - start_time)
                return result
            else:
                return self.action(*args)

        except Exception as exc:
            # Re-raise exception with operation details if not handled
            if not isinstance(exc, OperationError):
                exc = OperationError(exc).with_traceback(sys.exc_info()[2])

            exc.add_location(self)
            raise exc

    def action(self, *args):
        """
        Perform action of operation
        :param args:
        :param kwargs:
        :return:
        """
        raise NotImplementedError()

    def add_child_operation(self, operation, **kwargs):
        """
        Converts operation and adds to list of child operations
        :param operation:
        :param kwargs:
        :return:
        """
        operation = convert_to_operation(operation, **kwargs)
        if operation:
            self.child_operations.append(operation)
        return operation

    def search(self, condition):
        """
        Return list of operations contained within this operation (including self) that match condition
        :param condition: Callable which takes operation instance and returns boolean
        :return:
        """
        # Get child operation matches
        matches = [match_op for child_op in self.child_operations for match_op in child_op.search(condition)]
        # add self if match
        if condition(self):
            matches = [self] + matches
        return matches

    #############################################################################################
    #   PROFILING
    #############################################################################################
    @property
    def unique_pstat(self):
        """
        Whether each instance of this operation should have its own unique profile data or share it with other instances
        with same configuration.
        By default, compound operations (with any child operations registered) have unique profile stats
        :return:
        """
        return bool(self.child_operations)

    def enable_profiling(self):
        self.clear_profile_stats()
        self.profiling_enabled = True
        for operation in self.child_operations:
            operation.enable_profiling()

    def disable_profiling(self):
        self.profiling_enabled = False
        for operation in self.child_operations:
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
        # Verify profile data
        verify_profile_data(profile_data)
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
        # operation_ids set is used to keep track of which operations have already added their profile data
        profile_data = {'operation_ids': set()}
        self.add_profile_data(profile_data, None)
        profile_data.pop('operation_ids')
        return profile_data

    def add_profile_data(self, profile_data, caller):
        """

        :param dict profile_data: Current profile data dictionary
        :param Operation, None caller: parent calling operation
        :return:
        """
        self.add_self_profile_data(profile_data, caller)
        # Add profile data for wrapped operations
        for operation in self.child_operations:
            operation.add_profile_data(profile_data,
                                       caller=self)

    def add_self_profile_data(self, profile_data, caller):
        """
        :param dict profile_data: Current profile data dictionary
        :param Operation, None caller: parent calling operation
        :return:
        """
        # Dont add to profile stats if not called
        if not self._call_count:
            return

        node_id = self.pstat_id

        # Only add this instance's profile data once
        if id(self) not in profile_data['operation_ids']:
            add_profile_stats(profile_data,
                              node_id,
                              self.get_execution_stats(),
                              primary=True)
            profile_data['operation_ids'].add(id(self))

        # add profile stats for caller
        if caller:
            stats_for_caller = caller.get_child_operation_stats(self)
            # Stats may be None if parent operation was never run, and dont add stats if run count is 0
            if stats_for_caller and stats_for_caller[0]:
                add_profile_stats(profile_data[node_id][4], caller.pstat_id, stats_for_caller, primary=False)

    def get_child_operation_stats(self, child_operation):
        """
        Get child operation execution stats due to calling by this parent operation
        May not exist if this operation was never executed
        :param BaseOperation child_operation:
        :return:
        """
        return self._child_execution_stats.get(id(child_operation), None)

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
        return (self._call_count, self._call_count, self.get_execute_time(), self.get_cumulative_time())

    def get_total_overhead_time(self):
        """
        Get overhead time of this operation and all child operations
        Value may not reflect overhead time associated only with this operation execution,
        if any child operations are used outside of this operation
        :return:
        """
        overhead_times = {}
        self.collect_overhead_times(overhead_times)
        return sum(overhead_times.values())

    def collect_overhead_times(self, overhead_times):
        """
        Add overhead time of this operation and all child operations to collection.
        Dictionary mapping of operation ID to overhead time for operation is used so overhead time for same operation
        isn't counted multiple times (for when operation instance is reused in multiple places)
        :param dict overhead_times: Mapping of operation ID to overhead time for operation
        :return:
        """
        overhead_times[id(self)] = self._overhead_time
        for child in self.child_operations:
            child.collect_overhead_times(overhead_times)

    def get_cumulative_time(self):
        """
        Get total execution time of this operation (including wrapped sub-operations)
        :return:
        """
        return self._cumulative_time

    def get_execute_time(self):
        """
        Get execution time of just this operation (not including any wrapped sub-operations)
        :return:
        """
        return self.get_cumulative_time() - sum(child_stat[3] for child_stat in self._child_execution_stats.values())

    @property
    def pstat_id(self):
        """
        Get operation ID for profiling, in format:
        (module_name, line_number, function_name)
        :return:
        """
        return (type(self).__name__,
                id(self) if self.unique_pstat else id(type(self)),
                self.auto_desc(max_len=120))

    def clear_profile_stats(self):
        """
        Reset execution profiling statistics
        :return:
        """
        self.profiling_active = False
        self._cumulative_time = self._call_count = self._overhead_time = 0
        self._child_execution_stats = {}
        for operation in self.child_operations:
            operation.clear_profile_stats()

    #############################################################################################
    #   Graphing
    #############################################################################################

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
        node = Node(name=randomstring(10), label=self.auto_desc())
        graph.add_node(node)
        return node, node

    #############################################################################################
    #   REPRESENTATION
    #############################################################################################

    def short_description(self):
        """
        Shorter description of operation, useful for simplifying description of compound operations which
        can get unwieldy
        :return:
        """
        return self.description()

    def description(self):
        """
        Full description of operation
        :return:
        """
        return type(self).__name__

    def auto_desc(self, max_len=180):
        """
        Get description of operation. Truncates if above certain length
        :return:
        """
        desc = self.description()
        if len(desc) > max_len:
            desc = self.short_description()
            if len(desc) > max_len:
                desc = desc[:max_len-3] + '...'
        return desc

    def __repr__(self):
        return self.auto_desc()


class Operation(BaseOperation):
    """
    Parent class for most operations.
    Adds operator overloading to base Operation functionality, enabling chaining and construction of logic using
    standard operators, such as:
     - operations to be chained together (output of first goes to input of second) (>>)
     - Perform bitwise operator (vector or scalar) on output of two operations (&, |, ~)
     - Perform arithmetic (vector or scalar) on output of two operations (+, -, *, /)
     - Comparison (>, <, <=, >=, ==)
    Operation instances are not hashable since they are also not comparable (equality operator overloaded)
    """

    # CHAINING
    def __rshift__(self, other):
        # Ignore chaining with None or Pass
        if other is None or isinstance(other, Pass):
            return self
        # If self is Pass, adopt new operation
        elif isinstance(self, Pass):
            return convert_to_operation(other)
        else:
            # Create new chain of operations
            return ChainedOperations(*(self.child_operations if isinstance(self, ChainedOperations) else [self]),
                                     *(other.child_operations if isinstance(other, ChainedOperations) else [other]))

    # NEGATE
    def __neg__(self):
        return NegatedOperation(self)

    # CONTAINS/IN
    def __contains__(self, item):
        # IN operator cannot be deferred (coerces output to Bool, so cannot return an IN instance)
        # Use In operation instead
        raise Exception('Use "In" operation instead of "in" operator')

    # SLICING
    def __getitem__(self, item):
        return SlicedOperation(self, item)

    # BITWISE
    def __invert__(self):
        return InvertedOperation(self)

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
        self.op1 = self.add_child_operation(op1)
        self.op2 = self.add_child_operation(op2)
        # Store operator string
        if operator_str not in self.OPERATORS:
            raise  ValueError('{} is not a valid operator string'.format(operator_str))
        self.operator = self.OPERATORS[operator_str]
        self.operator_str = operator_str

    def action(self, *args):
        # Apply operator on output of two operands
        return self.operator(self.op1(*args), self.op2(*args))

    def description(self):
        return '({}) {} ({})'.format(self.op1, self.operator_str, self.op2)


class SingleOperandOperator(Operation):
    """
    Base class for operators which operate on single operand (INVERT, NEG, SLICE)
    Inherits type translations from single contained operation
    """

    def __init__(self, op):
        super().__init__()
        self.operation = self.add_child_operation(op)


class InvertedOperation(SingleOperandOperator):
    """Bitwise Invert operator (not for boolean)"""

    def action(self, *args):
        return ~self.operation(*args)

    def description(self):
        return '~({})'.format(self.operation)


class NegatedOperation(SingleOperandOperator):
    """Invert operator"""

    def action(self, *args):
        return -self.operation(*args)

    def description(self):
        return '-({})'.format(self.operation)


class SlicedOperation(SingleOperandOperator):
    """
    Enables string slicing of operator return value
    Can do vectorised pd.str.slice, or standard string slicing on scalar values
    """

    def __init__(self, op, key):
        """

        :param op: Operation being sliced
        :param key: Slice or indexing key
        """
        if not isinstance(key, (slice, int)):
            self.error(ValueError, 'Indexing key must be integer or slice')
        self.key = key
        super().__init__(op)

    def action(self, *args):
        op_result = self.operation(*args)

        # Check and perform Pandas series string slicing
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
    Holds operations to be chained together
    """

    def __init__(self, *operations):
        """

        :param Operation operations: Operations to chain together
        """
        super().__init__()
        if len(operations) < 2:
            raise ValueError('Must initialise {} with at least 2 operations'.format(type(self).__name__))
        for operation in operations:
            self.add_child_operation(operation)

    def action(self, value):
        """
        Return chained output. Only supports single input value
        :param value:
        :return:
        """
        for operation in self.child_operations:
            value = operation(value)
        return value

    def add_to_graph(self, graph):
        from pydot import Edge, Cluster
        # Create Subgraph/cluster to contain operation chain
        # subgraph = Cluster(graph_name=randomstring(10), label=self.short_description())
        # Create sequence of child operation nodes in subgraph
        first_tail, prev_head = self.child_operations[0].add_to_graph(graph)
        for operation in self.child_operations[1:]:
            # Create new node for operation and edge to previous node
            tail, head = operation.add_to_graph(graph)
            graph.add_edge(Edge(prev_head, tail))
            prev_head = head

        # graph.add_subgraph(subgraph)
        return first_tail, prev_head

    def short_description(self):
        return 'Chain of {} operations'.format(len(self.child_operations))

    def description(self):
        return ' --> '.join('({})'.format(operation) for operation in self.child_operations)

    # Iteration disabled because causes operation to be detected as list-like by Pandas (and maybe elsewhere) which
    # has undesired behaviour
    # def __iter__(self):
    #     """
    #     :return:
    #     """
    #     for operation in self.child_operations:
    #         yield operation

    def __len__(self):
        # Get length of pipeline
        return len(self.child_operations)

    # SLICING
    def __getitem__(self, item):
        """
        Allow indexing / slicing of pipeline
        :param item:
        :return:
        """
        sliced_operations = self.child_operations[item]
        # Single instance
        if isinstance(sliced_operations, BaseOperation):
            return sliced_operations
        # Slice of length 1
        elif len(sliced_operations) == 1:
            return sliced_operations[0]
        else:
            return ChainedOperations(*sliced_operations)


class Value(Operation):
    """
    Allows specifying static values (strings, numbers, etc) which can be used in arithmetic or comparison with other operations
    Required when using 'in' operator
    """

    def __init__(self, value):
        super().__init__()
        self.value = value

    def action(self, *args):
        # Return static value regardless of of input
        return self.value

    def description(self):
        return 'Value: "{}"'.format(self.value)


class Lambda(Operation):
    """
    Used to wrap a generic callable as an Operation instance.
    """

    def __init__(self, func, description=None):
        """

        :param func: Callable which takes input value, performs processing logic and returns output
        :param str description: Description of what function does. Function name is used if not specified
        """
        super().__init__()
        self.func = func
        self._description = description or func.__name__

    def action(self, *args):
        return self.func(*args)

    def description(self):
        return self._description


class Pass(Operation):
    """
    Acts as a special transparent operation, returns input value with no change, and is removed/ignored in an operation
    chain. Has a Falsey value (can be used to check if operation exists/does anything)
    """

    def __bool__(self):
        return False

    def action(self, value):
        return value


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


def add_profile_stats(container, pstat_id, new_stats, primary=True):
    """
    Create new stats entry or add to existing
    :param dict container:
    :param int, tuple pstat_id:
    :param tuple new_stats: stats in form (call_count, call_count, tottime, cumtime)
    :param bool primary: Whether this is adding primary pstat (not for caller)
    :return:
    """
    if pstat_id in container:
        existing_stats = container[pstat_id]
        merged_stats = tuple(existing_stats[i] + new_stats[i] for i in range(4))
        container[pstat_id] = merged_stats + (existing_stats[4],) if primary else merged_stats
        # for i in range(4):
        #     existing_stats[i] += new_stats[i]
    else:
        # Make copy of new stats list so original isnt mutated later
        container[pstat_id] = new_stats + ({},) if primary else new_stats


def get_stat_delta(before_stats, after_stats):
    """
    Perform element-wise subtraction of stat tuple components
    :param tuple before_stats:
    :param tuple after_stats:
    :return:
    """
    return tuple(after_stat - before_stat for before_stat, after_stat in zip(before_stats, after_stats))


def verify_profile_data(profile_data):
    """
    Verify PSTAT profile data dictionary
    :param profile_data:
    :return:
    """
    for stat_id, stat_data in profile_data.items():
        verify_stat_data(stat_id, stat_data)
        # Verify caller data
        if stat_data[4]:
            caller_data_sum = [0,0,0,0]
            for caller_id, caller_data in stat_data[4].items():
                verify_stat_data(caller_id, caller_data)
                for i in range(4):
                    caller_data_sum[i] = caller_data_sum[i] + caller_data[i]

            for i in range(4):
                if stat_data[i] != caller_data_sum[i]:
                    raise InvalidProfileDataError(
                        'Profile data appears to be incorrect for {}:\n{}\n{} != {}'.format(stat_id,
                                                                                            pprint.pformat(stat_data),
                                                                                            stat_data[:4],
                                                                                            caller_data_sum))

def verify_stat_data(stat_id, stat_data):
    """
    Verify single profile execution stat data
    :param stat id:
    :param tuple stat_data: (call_count, call_count, exec time, cum time)
    :return:
    """
    if any(val < 0 for val in stat_data[:4]) or not stat_data[2] <= stat_data[3]:
        raise InvalidProfileDataError('Invalid profile stat data: {}: {}'.format(stat_id, stat_data[:4]))
