from etl_framework.operations.base import BaseOperation, ScalarOrVectorOperation, TypeTranslations
from etl_framework.exceptions import ETLConfigurationError
from etl_framework.context import transform_context
import pandas as pd


class Field(BaseOperation):
    """
    Operation used to select field to translate from Dataframe to Column or Row to Value
    NOT a wrapper, instead can be chained
    """
    calling_translations = {
        'dataframe': 'column',
        'row': 'value'
    }

    def __init__(self, field_name):
        """

        :param field_name: Name of column to select
        """
        if not isinstance(field_name, str):
            raise ETLConfigurationError('Field name must be string')
        self.field_name = field_name

    def __call__(self, multiple_fields):
        """
        :param multiple_fields: Dataframe or Row containing multiple fields
        return:
        """
        # Make copy of column to avoid SettingWithCopyWarning
        if isinstance(multiple_fields, pd.DataFrame):
            return multiple_fields[self.field_name]#.copy()
        else:
            return multiple_fields[self.field_name]

    def __str__(self):
        return 'Field: "{}"'.format(self.field_name)


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


class Length(ScalarOrVectorOperation):
    """
    Calaculate string length of column
    """
    def __call__(self, value):
        """

        :param value: Either string column or scalar value
        :return:
        """
        if self.input_type == 'column':
            return value.str.len()
        else:
            return len(value)

    def __str__(self):
        return 'len()'


class Lambda(BaseOperation):
    """
    Allows for custom simple transform logic
    Can optionally provide type translation for compatability validation

    """
    def __init__(self, func, description, type_translation=None):
        """

        :param func: Callable which takes input value, performs processing logic and returns output
        :param description: Description of what function does
        :param type_translation: Optionally provide type translation of custom function
        """
        self.func = func
        self.description = description
        if type_translation:
            self.calling_translations = type_translation

    def __call__(self, value):
        return self.func(value)

    def __str__(self):
        return self.description


class IsIn(ScalarOrVectorOperation):
    """
    Operation for performing membership check of set of values
    """
    calling_translations = {
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, values, input_type='column'):
        """

        :param values: sequence of values to check for membership of (or callable which returns list-like)
        :param str input_type: Input type (column or value)
        """
        self.values = values
        super().__init__(input_type)

    def __call__(self, value):
        """

        :param value: Series or scalar value
        :return: boolean Series or scalar
        """
        test_values = self.values(value) if callable(self.values) else self.values
        if self.input_type == 'column':
            return value.isin(test_values)
        else:
            return value in test_values

    def __str__(self):
        return 'IS IN {}'.format(self.values)


class Map(ScalarOrVectorOperation):
    """
    Provide mapping dictionary which will be used to Convert column or scalar values
    Can specify logic for what happens when lookup values are missing (raise error, pass through key, use default)
    """
    ORIGINAL = object()
    ERROR = object()

    calling_translations = {
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, mapping, input_type='column', missing_value=None):
        """

        :param dict mapping: Value mapping dictionary
        :param str input_type: Input type (column or value)
        :param missing_value: Default value to set if mapping key is missing.
        Set to Map.ERROR to raise error,
        Map.ORIGINAL to pass through original value,
        or leave as None for default Pandas behaviour (set missing values as NaN)
        """
        if missing_value is not None:
            if missing_value == self.ORIGINAL:
                mapping = DictWithPassthrough(**mapping)
            elif missing_value == self.ERROR:
                mapping = DictWithError(**mapping)
            else:
                mapping = DictWithDefault(missing_value, **mapping)

        self.mapping = mapping
        super().__init__(input_type)

    def __call__(self, value):
        """Apply mapping to column or value"""
        if self.input_type == 'column':
            return value.map(self.mapping)
        else:
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


class NoOp(BaseOperation):
    """
    Dummy operation that does nothing but pass input to output
    Can be useful as initial operation in Transform to start chain
    """
    calling_translations = TypeTranslations.GENERIC_TYPE_TRANSLATIONS

    def __call__(self, value):
        return value

    def __str__(self):
        return 'NoOp'


