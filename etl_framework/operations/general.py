"""
Operations for controlling flow of pipeline
"""
import logging
from etl_framework.context import transform_context
from etl_framework.operations import Operation

log = logging.getLogger(__name__)


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
        super().__init__()
        self.key_name = key_name

    def action(self, *args):
        return transform_context[self.key_name]

    def description(self):
        return 'Transform Context value: "{}"'.format(self.key_name)


class MapValue(Operation):
    """
    Provide mapping dictionary which will be used to translate values
    Can specify logic for what happens when lookup values are missing (raise error, pass through key, use default)
    """
    ORIGINAL = object()
    ERROR = object()

    def __init__(self, mapping,  missing_value=ERROR):
        """

        :param dict mapping: Value mapping dictionary
        :param missing_value: Determines behaviour for when mapping key is missing:
        Map.ERROR: Raise KeyError
        Map.ORIGINAL: to pass through original value,
        Other: Use this value as default
        """
        super().__init__()
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
        super().__init__()
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
        super().__init__()
        self.filter_func = self.add_child_operation(filter_func)

    def action(self, values):
        """

        :param iterable values:
        :return:
        """
        return (val for val in values if self.filter_func(val))

    def description(self):
        return 'Filter values using function: "{}"'.format(self.filter_func)


class ArgsToList(Operation):
    """
    Simple operation to convert function positional arguments to a list
    """
    def action(self, *args):
        return args


class Print(Operation):
    """
    Prints and returns input value. Useful for debugging
    """
    def action(self, value):
        print(value)
        return value


class RaiseException(Operation):
    """
    Raises provided exception
    """
    def __init__(self, exception):
        """

        :param Exception exception: Exception to raise
        """
        super().__init__()
        self.exception =exception

    def action(self, *args):
        raise self.exception


class CallMethod(Operation):
    """
    Call a method on input object (e.g. Series or Dataframe)
    Method name is provided as string and can contain chained references, e.g. 'attr.method'
    Can also specify args and kwargs to provide to method call
    """
    def __init__(self, method_name, *args, **kwargs):
        """

        :param str method_name: Name of method to call (can contain dots for chained reference)
        :param args: Positional arguments to provide
        :param kwargs: Keyword arguments to provide
        """
        super().__init__()
        self.method_name = method_name
        self.args = args
        self.kwargs = kwargs

    def action(self, obj):
        """
        Input object to call method on
        :param obj:
        :return:
        """
        method = obj
        for method_component in self.method_name.split('.'):
            method = getattr(method, method_component)

        return method(*self.args, **self.kwargs)

    def description(self):
        desc = 'Call method: "{}"'.format(self.method_name)
        if self.args:
            desc += ' with args: {}'.format(self.args)
        if self.kwargs:
            desc += ' and kwargs: {}'.format(self.kwargs)
        return desc