"""
Operations for controlling flow of pipeline
"""
import copy, logging
from etl_framework.context import transform_context
from etl_framework.operations import Operation, CompoundOperation
from etl_framework.operations.types import TypeTranslations
from etl_framework.utils import LogDuration, randomstring

log = logging.getLogger(__name__)


class NoOp(Operation):
    """
    Returns input value with no change
    Can be useful as initial operation in Transform to start chain
    """
    calling_translations = TypeTranslations.GENERIC_TYPE_TRANSLATIONS

    def action(self, value):
        return value

    def description(self):
        return 'Input'


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
        self.false_operation = false_operation or NoOp()
        self.true_operation = true_operation
        self.condition = condition
        super().__init__([self.false_operation, self.true_operation, self.condition])

    def action(self, value):
        if self.condition(value):
            return self.true_operation(value)
        else:
            return self.false_operation(value)

    def description(self):
        return 'If {} then ({}), else ({})'.format(str(self.condition), self.true_operation, self.false_operation)


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
        super().__init__(self.fork_operations)

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
        from pydot import Edge, Node
        # Create Fork node
        fork_node, fork_node = super().add_to_graph(graph)
        for operation in self.fork_operations:
            start_node, end_node = operation.add_to_graph(graph)
            graph.add_edge(Edge(fork_node, start_node,
                                ltail=fork_node.obj_dict['parent_graph'].get_name(),
                                lhead=start_node.obj_dict['parent_graph'].get_name()))
        return fork_node, None

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