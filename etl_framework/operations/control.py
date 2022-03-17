"""
Operations to control flow of pipeline
"""
import copy
import logging

from etl_framework.operations import Pass, Operation
from etl_framework.utils import randomstring, LogDuration

log = logging.getLogger(__name__)


class If(Operation):
    """
    Conditional statement to choose between executing one or another operation
    """

    def __init__(self, condition, true_operation, false_operation=None):
        """

        :param condition: Callable which takes input and returns True or False
        :param true_operation: Operation to execute if condition returns True
        :param false_operation: Operation to execute if condition returns False (defaults to no action)
        """
        super().__init__()
        self.false_operation = self.add_child_operation(false_operation or Pass())
        self.true_operation = self.add_child_operation(true_operation)
        self.condition = self.add_child_operation(condition)

    def action(self, value):
        if self.condition(value):
            return self.true_operation(value)
        else:
            return self.false_operation(value)

    def description(self):
        desc = 'If {}, \nThen: ({})'.format(self.condition, self.true_operation)
        if self.false_operation:
            desc += ', \nElse: ({})'.format(self.false_operation)
        return desc

    def short_description(self):
        return 'If {}'.format(str(self.condition))

    def add_to_graph(self, graph):
        from pydot import Edge, Node
        # Create start If node
        if_node = Node(name=randomstring(10), label=self.short_description())
        graph.add_node(if_node)
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


class SwitchCase(Operation):
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
        super().__init__()
        self.default = self.add_child_operation(default or Pass())
        self.case_mapping = {key: self.add_child_operation(operation) for key, operation in case_mapping.items()}
        self.key_operation = self.add_child_operation(key_operation, wrap_value=False)

    def action(self, value):
        case_value = self.key_operation(value)
        if case_value in self.case_mapping:
            return self.case_mapping[case_value](value)
        else:
            return self.default(value)

    def description(self):
        return 'Switch on value of: "{}"'.format(self.key_operation)

    def add_to_graph(self, graph):
        from pydot import Edge, Node
        DEFAULT_KEY = '_default_'
        # Create Start switch node
        start_switch_node = Node(name=randomstring(10), label=self.auto_desc())
        graph.add_node(start_switch_node)
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


class Fork(Operation):
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
        super().__init__()
        if len(fork_operations) < 2:
            self.error(ValueError, 'Provide at least 2 operations to Fork')
        self.fork_operations = [self.add_child_operation(operation) for operation in fork_operations]

    def action(self, input_val):
        """

        :param input_val: Input value to provide to all operation chains
        :return:
        """
        outputs = []

        # Execute chain of operations
        for i, operation in enumerate(self.fork_operations):
            value = operation(copy.deepcopy(input_val))
            outputs.append(value)
        return outputs

    # def add_profile_data(self, profile_data, actual_caller=None, proxy_caller=None, transparent=None):
    #     """
    #
    #     :param dict profile_data:
    #     :param CompoundOperation actual_caller:
    #     :param CompoundOperation proxy_caller:
    #     :param bool transparent:
    #     :return:
    #     """
    #     # Force normally 'transparent' fork operations (e.g. THEN) to add their own profile data so each fork is bundled
    #     # Add profile data for self
    #     super().add_profile_data(profile_data, actual_caller=actual_caller, proxy_caller=proxy_caller)
    #     # Add profile data for wrapped operations
    #     for operation in self.wrapped_operations:
    #         operation.add_profile_data(profile_data,
    #                                    actual_caller=self,
    #                                    proxy_caller=self,
    #                                    transparent=False)

    def add_to_graph(self, graph):
        from pydot import Edge, Node
        # Create end node for Fork
        output_node = Node(name=randomstring(10), label='List of results')
        graph.add_node(output_node)
        # Create Fork node
        fork_node = Node(name=randomstring(10), label=self.short_description())
        graph.add_node(fork_node)
        # Add fork operations to graph
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


class CollectFrom(Operation):
    """
    Runs iterable operation and collects results into a tuple
    """
    def __init__(self, operation):
        """

        :param operation: Operation which takes some single input and returns iterator of values
        """
        super().__init__()
        self.operation = self.add_child_operation(operation)

    def action(self, input_val):
        return tuple(self.operation(input_val))

    def description(self):
        return 'Collect values from iterable: {}'.format(self.operation)

    def short_description(self):
        return 'Collect values from iterable'

    def add_to_graph(self, graph):
        # Create Subgraph/cluster to contain wrapped operation
        from pydot import Cluster
        subgraph = Cluster(graph_name=randomstring(10),
                           label=self.short_description())
        start_node, end_node = self.operation.add_to_graph(subgraph)
        graph.add_subgraph(subgraph)
        return start_node, end_node


class Map(Operation):
    """
    Apply operation to each element of input
    Currently needs to evaluate all results at once in order to profile execution stats properly (otherwise actual
    processing will occur when operation further down the chain evaluates the iterator)
    TODO: Try work out how to properly profile generators??
    """

    def __init__(self, operation):
        """

        :param operation: Operation to run on each iterator item
        """
        super().__init__()
        self.operation = self.add_child_operation(operation)

    def action(self, iterable):
        return [self.operation(item) for item in iterable]

    def description(self):
        return 'Map on each input element: {}'.format(self.operation)

    def short_description(self):
        return 'Map function on each input element'

    def add_to_graph(self, graph):
        # Create Subgraph/cluster to contain wrapped operation
        from pydot import Cluster
        subgraph = Cluster(graph_name=randomstring(10),
                           label=self.short_description())
        start_node, end_node = self.operation.add_to_graph(subgraph)
        graph.add_subgraph(subgraph)
        return start_node, end_node
