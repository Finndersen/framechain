"""
Operations to control flow of pipeline
"""
import copy
import logging

from etl_framework.operations import CompoundOperation, Pass, Operation, convert_to_operation
from etl_framework.utils import randomstring, LogDuration

log = logging.getLogger(__name__)


class If(CompoundOperation):
    """
    Conditional statement to choose between executing one or another operation
    """
    calling_translations = {
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, condition, true_operation, false_operation=None):
        """

        :param condition: Callable which takes input and returns True or False
        :param true_operation: Operation to execute if condition returns True
        :param false_operation: Operation to execute if condition returns False (defaults to no action)
        """
        self.false_operation = false_operation or Pass()
        self.true_operation = true_operation
        self.condition = convert_to_operation(condition)
        super().__init__(self.false_operation, self.true_operation, self.condition)

    def action(self, value):
        if self.run_wrapped_operation(self.condition, value):
            return self.run_wrapped_operation(self.true_operation, value)
        else:
            return self.run_wrapped_operation(self.false_operation, value)

    def description(self):
        return 'If {}, \nThen: ({}), \nElse: ({})'.format(str(self.condition), self.true_operation,
                                                          self.false_operation)

    def short_description(self):
        return 'If {}'.format(str(self.condition))

    def add_to_graph(self, graph):
        from pydot import Edge, Node
        # Create start If node
        if_node, _ = super().add_to_graph(graph)
        # create End If node
        end_if_node = Node(name=randomstring(10), label='EndIf')
        graph.add_node(end_if_node)

        true_start, true_end = self.true_operation.add_to_graph(graph)
        false_start, false_end = self.false_operation.add_to_graph(graph)

        graph.add_edge(Edge(if_node, true_start, label='True'))
        graph.add_edge(Edge(if_node, false_start, label='False'))
        graph.add_edge(Edge(true_end, end_if_node))
        graph.add_edge(Edge(false_end, end_if_node))

        return if_node, end_if_node


class SwitchCase(CompoundOperation):
    """
    Operation which works like a Switch-Case statement.
    Contains a mapping of values to operations to run if input is equal to that value
    """

    def __init__(self, key_operation, case_mapping, default=None):
        """
        :param Operation key_operation: Transform to perform on input value to get mapping key
        :param dict case_mapping: Mapping of case values to associated operations
        :param default: Default operation to run if value is not matched
        """
        self.default = default or Pass()
        self.case_mapping = case_mapping
        self.key_operation = key_operation
        super().__init__(*list(case_mapping.values()), default, key_operation)

    def action(self, value):
        case_value = self.run_wrapped_operation(self.key_operation, value)
        if case_value in self.case_mapping:
            return self.run_wrapped_operation(self.case_mapping[case_value], value)
        else:
            return self.run_wrapped_operation(self.default, value)

    def short_description(self):
        return 'Switch on value of: \n"{}"'.format(self.key_operation)

    def add_to_graph(self, graph):
        from pydot import Edge, Node
        DEFAULT_KEY = '_default_'
        # Create Start switch node
        start_switch_node, _ = super().add_to_graph(graph)
        # Create end switch node
        end_switch_node = Node(name=randomstring(10), label='End Switch')
        graph.add_node(end_switch_node)

        for case, operation in {**self.case_mapping, DEFAULT_KEY: self.default}.items():
            start_node, end_node = operation.add_to_graph(graph)
            # Add edge joining Switch node start of case operation
            graph.add_edge(Edge(start_switch_node, start_node,
                                label='Default' if case == DEFAULT_KEY else 'Case: "{}"'.format(case)))
            # Add edge joining end of case operation to end switch node
            graph.add_edge(Edge(end_node, end_switch_node))

        return start_switch_node, end_switch_node


class Fork(CompoundOperation):
    """
    Transformation which allows creating a fork in the execution pipeline
    Causes input value to be copied and provided to multiple operation chains
    Will return a list containing outputs of each operation chain
    Each chain should end in an Output Generator because it can be cumbersome to aggregate or do further
    processing on the output sequence from this operation
    """

    def __init__(self, *fork_operations):
        """

        :param Operation fork_operations: Sequence of operation chains to execute with single input.
        """
        if len(fork_operations) < 2:
            self.error(ValueError, 'Provide at least 2 operations to Fork')
        self.fork_operations = list(fork_operations)
        super().__init__(*self.fork_operations)

    def action(self, input_val):
        """

        :param input_val: Input value to provide to all operation chains
        :return:
        """
        outputs = []

        # Execute chain of operations
        for i, operation in enumerate(self.fork_operations):
            value = copy.deepcopy(input_val)
            with LogDuration(log, 'Running fork #{} operation: {}'.format(i, operation)):
                value = self.run_wrapped_operation(operation, value)
            outputs.append(value)
        return outputs

    def add_profile_data(self, profile_data, actual_caller=None, proxy_caller=None, transparent=None):
        """

        :param dict profile_data:
        :param Operation actual_caller:
        :param Operation proxy_caller:
        :param bool transparent:
        :return:
        """
        # Force normally 'transparent' fork operations (e.g. THEN) to add their own profile data so each fork is bundled
        # Add profile data for self
        super().add_profile_data(profile_data, actual_caller=actual_caller, proxy_caller=proxy_caller)
        # Add profile data for wrapped operations
        for operation in self.wrapped_operations:
            operation.add_profile_data(profile_data,
                                       actual_caller=self,
                                       proxy_caller=self,
                                       transparent=False)

    def add_to_graph(self, graph):
        from pydot import Edge, Node
        # Create end node for Fork
        output_node = Node(name=randomstring(10), label='List of results')
        graph.add_node(output_node)
        # Create Fork node
        fork_node, _ = super().add_to_graph(graph)
        for operation in self.fork_operations:
            start_node, end_node = operation.add_to_graph(graph)
            # Add edge joining Fork node start of fork operation
            graph.add_edge(Edge(fork_node, start_node))
            # Add edge joining end of fork operation to results node
            graph.add_edge(Edge(end_node, output_node))

        return fork_node, output_node

    def short_description(self):
        return 'Fork into {} chains'.format(len(self.fork_operations))

    def description(self):
        return 'Fork into {} chains: {}'.format(len(self.fork_operations), '\n'.join('#{}: ({})'.format(i, operation)
                                                                                     for i, operation in
                                                                                     enumerate(self.fork_operations)))


class Collect(Operation):
    """
    Collects an iterable into a tuple of values
    """

    def action(self, iterable):
        return tuple(iterable)


class Iterate(Operation):
    """
    Iterates over provided iterator and execute provided operation on each element
    Returns a generator of result of each item after being transformed by operation
    """

    def __init__(self, operation):
        """

        :param operation: Operation to run on each iterator item
        """
        self.operation = operation

    def action(self, iterable):
        for item in iterable:
            yield self.operation(item)
