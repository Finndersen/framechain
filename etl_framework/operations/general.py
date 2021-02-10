"""
Operations for controlling flow of pipeline
"""
import copy, logging
from etl_framework.context import transform_context
from etl_framework.operations import Operation, CompoundOperation
from etl_framework.operations.types import TypeTranslations
from etl_framework.utils import LogDuration, randomstring

log = logging.getLogger(__name__)


class Pass(Operation):
    """
    Returns input value with no change
    Can be useful as initial operation in Transform to start chain
    """
    calling_translations = TypeTranslations.GENERIC_TYPE_TRANSLATIONS

    def action(self, value):
        return value

    def description(self):
        return 'Pass'


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
        self.condition = condition
        super().__init__(self.false_operation, self.true_operation, self.condition)

    def action(self, value):
        if self.condition(value):
            return self.true_operation(value)
        else:
            return self.false_operation(value)

    def description(self):
        return 'If {}, \nThen: ({}), \nElse: ({})'.format(str(self.condition), self.true_operation, self.false_operation)

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
        case_value = self.key_operation(value)
        if case_value in self.case_mapping:
            return self.case_mapping[case_value](value)
        else:
            return self.default(value)

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

        # Execute chain of operations (TODO: initialise new Pipeline instance to handle this?)
        for i, operation in enumerate(self.fork_operations):
            value = copy.deepcopy(input_val)
            with LogDuration(log, 'Running fork #{} operation: {}'.format(i, operation)):
                value = operation(value)
            outputs.append(value)
        return outputs

    def add_profile_data(self, profile_data, caller=None, add_self_data=True):
        """
        Force normally 'transparent' fork operations (e.g. THEN) to add their own profile data so each fork is bundled
        :param profile_data:
        :param caller:
        :param bool add_self_data: Whether this operation wrapper should include its own profile stats, or be
        'transparent'
        :return:
        """
        profile_data = Operation.add_profile_data(self, profile_data, caller=caller,
                                                  add_self_data=add_self_data)
        for operation in self.wrapped_operations:
            profile_data = operation.add_profile_data(profile_data, self if add_self_data else caller,
                                                      add_self_data=True)
        return profile_data

    def add_to_graph(self, graph):
        from pydot import Edge, Node, Cluster
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
                                                       for i, operation in enumerate(self.fork_operations)))


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
        self.value = value

    def action(self, *args, **kwargs):
        # Return static value regardless of of input
        return self.value

    def description(self):
        # if isinstance(self.value, str):
        return 'Value: "{}"'.format(self.value)
        # else:
        #     return str(self.value)


class ContextValue(Operation):
    """
    Provides value from transform context dictionary
    Configure with callable that takes the context dictionary and returns desired value
    """
    calling_translations = {
        'dataframe': 'value',
        'column': 'value',
        'row': 'value',
        'value': 'value'
    }

    def __init__(self, key_name):
        """

        :param str key_name: key of value to extract from context dictionary
        """
        self.key_name = key_name

    def action(self, *args, **kwargs):
        return transform_context[self.key_name]

    def description(self):
        return 'Transform Context value: "{}"'.format(self.key_name)


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
        self.func = func
        self._description = description or func.__name__
        if type_translation:
            self.calling_translations = type_translation

    def action(self, value):
        return self.func(value)

    def description(self):
        return self._description


class Collect(Operation):
    """
    Collects an iterable into a list of values
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


class Map(Operation):
    """
    Provide mapping dictionary which will be used to translate values
    Can specify logic for what happens when lookup values are missing (raise error, pass through key, use default)
    """
    ORIGINAL = object()
    ERROR = object()

    calling_translations = {
        'value': 'value'
    }

    def __init__(self, mapping,  missing_value=None):
        """

        :param dict mapping: Value mapping dictionary
        :param missing_value: Determines behaviour for when mapping key is missing:
        Map.ERROR: Raise KeyError
        Map.ORIGINAL: to pass through original value,
        Other: Use this value as default
        """
        if missing_value == self.ORIGINAL:
            mapping = DictWithPassthrough(**mapping)
        elif missing_value == self.ERROR:
            mapping = DictWithError(**mapping)
        else:
            mapping = DictWithDefault(missing_value, **mapping)

        self.mapping = mapping

    def action(self, value):
        """Return mapped value"""
        return self.mapping[value]

    def description(self):
        return 'Map values: {}'.format(self.mapping if len(self.mapping) < 6 else '<Large mapping table>')


class Length(Operation):
    """
    Get length of input
    """
    def action(self, value):
        return len(value)


class DictWithDefault(dict):
    """
    Dict with default value which is returned if key is missing
    """

    def __init__(self, _default, **kwargs):
        self._default = _default
        super().__init__(**kwargs)

    def __missing__(self, key):
        return self._default


class DictWithPassthrough(dict):
    """
    Dict which returns original key if it is missing
    """

    def __missing__(self, key):
        return key


class DictWithError(dict):
    """
    Dict which raises error when key is missing
    """

    def __missing__(self, key):
        raise KeyError('Key: "{}" is missing from mapping dictionary'.format(key))


class GetAttr(Operation):
    """
    Return an attribute of input object
    """
    NOT_SPECIFIED = object()

    def __init__(self, attr_name, default=NOT_SPECIFIED):
        """

        :param str attr_name: Attribute name to return
        :param default: Default value to return if attribute does not exist
        """
        self.default = default
        self.attr_name = attr_name

    def action(self, obj):
        if self.default == self.NOT_SPECIFIED:
            return getattr(obj, self.attr_name)
        else:
            return getattr(obj, self.attr_name, self.default)

    def description(self):
        return 'Attribute: "{}"'.format(self.attr_name)