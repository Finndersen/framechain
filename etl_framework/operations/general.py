"""
Operations for controlling flow of pipeline
"""
import copy, logging
from etl_framework.context import transform_context
from etl_framework.operations import BaseOperation
from etl_framework.operations.base import TypeTranslations
from etl_framework.utils import LogDuration

log = logging.getLogger(__name__)


class Input(BaseOperation):
    """
    Returns input value with no change
    Can be useful as initial operation in Transform to start chain
    """
    calling_translations = TypeTranslations.GENERIC_TYPE_TRANSLATIONS

    def __call__(self, value):
        return value

    def __str__(self):
        return 'Input'


class If(BaseOperation):
    """
    Conditional statement to choose between executing one or another operation
    """
    calling_translations = {
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, condition, true_operation, false_operation=Input()):
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
        return 'If {} then ({}), else ({})'.format(str(self.condition), self.true_operation, self.false_operation)


class Fork(BaseOperation):
    """
    Transformation which allows creating a fork in the execution pipeline
    Causes input value to be copied and provided to multiple operation chains
    Will return a list containing outputs of each operation chain
    Each chain should end in an Output Generator because it can be cumbersome to aggregate or do further
    processing on the output sequence from this operation
    """
    def __init__(self, *operation_chains):
        """

        :param operation_chains: Sequence of operation chains to execute with single input. Each item can be a list of
        operations, or a single operation (potentially a chain of operations using >> operator)
        """
        self.operation_chains = [op_chain if isinstance(op_chain, (tuple, list)) else [op_chain]
                                 for op_chain in operation_chains]

    def __call__(self, input_val):
        """

        :param input_val: Input value to provide to all operation chains
        :return:
        """
        outputs = []

        # Execute chain of operations (TODO: initialise new Pipeline instance to handle this?)
        for i, op_chain in enumerate(self.operation_chains):
            value = copy.deepcopy(input_val)
            for operation in op_chain:
                with LogDuration(log, 'Running fork #{} operation: {}'.format(i, operation)):
                    value = operation(value)
            outputs.append(value)
        return outputs

    def __str__(self):
        return 'Fork into chains: {}'.format('\n'.join('#{}: ({})'.format(i,
                                                                          ','.join('({})'.format(str(op)) for op in op_chain))
                                                       for i, op_chain in enumerate(self.operation_chains)))


class Value(BaseOperation):
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

    def __call__(self, *args, **kwargs):
        # Return static value regardless of of input
        return self.value

    def __str__(self):
        # if isinstance(self.value, str):
        return 'Value: "{}"'.format(self.value)
        # else:
        #     return str(self.value)


class ContextValue(BaseOperation):
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

    def __call__(self, *args, **kwargs):
        return transform_context[self.key_name]

    def __str__(self):
        return 'Transform Context value: "{}"'.format(self.key_name)


class Lambda(BaseOperation):
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
        self.description = description or func.__name__
        if type_translation:
            self.calling_translations = type_translation

    def __call__(self, value):
        return self.func(value)

    def __str__(self):
        return self.description


class Collect(BaseOperation):
    """
    Collects an iterable into a list of values
    """

    def __call__(self, iterable):
        return tuple(iterable)


class Iterate(BaseOperation):
    """
    Iterates over provided iterator and execute provided operation on each element
    Returns a generator of result of each item after being transformed by operation
    """
    def __init__(self, operation):
        """

        :param operation: Operation to run on each iterator item
        """
        self.operation = operation

    def __call__(self, iterable):
        for item in iterable:
            yield self.operation(item)


class Map(BaseOperation):
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

    def __call__(self, value):
        """Return mapped value"""
        return self.mapping[value]

    def __str__(self):
        return 'Map values: {}'.format(self.mapping if len(self.mapping) < 6 else '<Large mapping table>')


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


class GetAttr(BaseOperation):
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

    def __call__(self, obj):
        if self.default == self.NOT_SPECIFIED:
            return getattr(obj, self.attr_name)
        else:
            return getattr(obj, self.attr_name, self.default)

    def __str__(self):
        return 'Attribute: "{}"'.format(self.attr_name)