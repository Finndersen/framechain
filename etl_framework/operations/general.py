"""
Operations for controlling flow of pipeline
"""
import logging
from etl_framework.context import transform_context
from etl_framework.operations import Operation
from etl_framework.operations.types import TypeTranslations

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

    def action(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def description(self):
        return self._description


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

    def __init__(self, mapping,  missing_value=ERROR):
        """

        :param dict mapping: Value mapping dictionary
        :param missing_value: Determines behaviour for when mapping key is missing:
        Map.ERROR: Raise KeyError
        Map.ORIGINAL: to pass through original value,
        Other: Use this value as default
        """
        if missing_value == self.ORIGINAL:
            dict_type = DictWithPassthrough()
        elif missing_value == self.ERROR:
            dict_type = DictWithError()
        else:
            dict_type = DictWithDefault(missing_value)

        # Dict cannot be initialised with non-string keywords, so must use update()
        dict_type.update(mapping)

        self.mapping = dict_type

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


class Filter(Operation):
    """
    Operation which takes sequence of values and filters according to provided function
    Returns list of filtered values
    """
    def __init__(self, filter_func):
        """

        :param filter_func: Function to check each value. Returns true for values to be kept
        """
        self.filter_func = filter_func

    def action(self, values):
        """

        :param iterable values:
        :return:
        """
        return [val for val in values if self.filter_func(val)]

    def description(self):
        return 'Filter values using function: "{}"'.format(self.filter_func)


class ArgsToList(Operation):
    """
    Simple operation to convert function positional arguments to a list
    """
    def action(self, *args):
        return args
