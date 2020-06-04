import pandas as pd
from etl_framework.exceptions import ETLConfigurationError
from etl_framework.operations.base import BaseOperation, TypeTranslations, WrappingTypeTranslatorMixin
from etl_framework.utils import Memoized, validate_callable


class OperationWrapper(BaseOperation, WrappingTypeTranslatorMixin):
    """
    Abstract base class for operation wrappers which and add extra functionality or information to existing operations
    Validates type compatability of wrapped operation, and operation operator overloading capability
    """

    def __init__(self, operation):
        """
        :param operation: Operation (e.g. transform, other OperationWrapper, etc) to wrap
        """
        self.validate_wrapped_operation_compatability(operation)
        self.operation = operation

    def __call__(self, *args, **kwargs):
        """

        :param args: Transformation primary argument (may not exist if MapFields came first)
        :param kwargs: extra transformation arguments potentially supplied from WithArgs or MapFields
        :return:
        """
        return self.operation(*args, **kwargs)

    def __str__(self):
        """
        Describes what the transform wrapper does
        :return:
        """
        return type(self).__name__


class Apply(OperationWrapper):
    """
    Wrapper which translates input from vector to scalar in Column axis
    e.g. Dataframe - > rows or Series -> values
    Also supports optional caching of transform output
    """
    wrapping_translations = {
        'dataframe': 'row',
        'column': 'value'
    }

    calling_translations = {
        'dataframe': 'column',
        'column': 'column'
    }

    def __call__(self, vector):
        """
        :param vector: Dataframe or Column (series)
        :return:
        """
        if isinstance(vector, pd.DataFrame):
            return vector.apply(lambda row: self.operation(row), axis=1)
        elif isinstance(vector, pd.Series):
            return vector.apply(lambda value: self.operation(value))
        else:
            raise ValueError('Input to Apply TransformWrapper should be DataFrame or Series')

    def __str__(self):
        return 'Apply ({}) to each row'.format(self.operation)


class Cached(OperationWrapper):
    """
    Transform wrapper which enables caching of output values
    Should wrap actual transform directly (not another TransformWrapper)
    Only compatible with Scalar (value) transforms
    """
    wrapping_translations = {
        'value': 'value'
    }

    calling_translations = wrapping_translations

    def __init__(self, operation):
        if isinstance(operation, OperationWrapper):
            raise ETLConfigurationError('{} TransformWrapper should be applied directly to Transform, not another wrapper'.format(type(self).__name__))
        super().__init__(Memoized(operation))

    def __str__(self):
        return '({}) with caching'.format(self.operation)


class MapArguments(OperationWrapper):
    """
    Transform wrapper which allows multiple Operation input arguments to be generated from the provided input,
    using specified operation/transform logic for each argument

    """
    wrapping_translations = {
        'dataframe': 'column',
        'row': 'value'
    }

    calling_translations = wrapping_translations

    def __init__(self, operation, **arg_mapping):
        """
        :param operation: Transform or TransformWrapper to supply argument values to
        :param callable, str arg_mapping: mapping of transform arg names to operations which take wrapper input and return desired value
        """
        self.arg_mapping = arg_mapping
        super().__init__(operation)

    def __call__(self, fields):
        """

        :param fields: Can be either entire dataframe or single row
        :return:
        """
        return self.operation(**{arg_name: arg_operation(fields)
                                 for arg_name, arg_operation in self.arg_mapping.items()})

    def __str__(self):
        return '({}) with arguments: {}'.format(self.operation,
                                                ', '.join(['{}=({})'.format(key,val) for key,val in self.arg_mapping.items()]))


class ColumnMask(OperationWrapper):
    """
    Masking wrapper which takes column, applies conditional logic to produce mask,
    and passes masked column to wrapped operation, and then integrate output values into returned series
    Full Dataframe mask wrapper would require knowledge of output column name, so then it effectively becomes a Transform Constructor
    """
    condition_input_type = 'column'
    wrapping_translations = calling_translations = {'column': 'column'}

    def __init__(self, condition, operation):
        """

        :param condition: Callable which takes column and returns boolean series mask
        :param operation: Operation to pass masked column to
        """
        # Validate type compatability of condition
        if self.condition_input_type not in TypeTranslations.get_for_operation(condition):
            raise ETLConfigurationError('Condition: {} is not compatible with {}'.format(condition, type(self).__name__))
        self.condition = condition
        super().__init__(operation)

    def __call__(self, input_column):
        # Get mask using condition
        mask = self.condition(input_column)
        # Provide masked column to operation
        transformed_values = self.operation(input_column.loc[mask])
        # Make copy of column to avoid SettingWithCopyWarning
        output_column = input_column.copy()
        # Integrate values back into original column
        output_column.loc[mask] = transformed_values
        return output_column

    def __str__(self):
        return 'Select values which match condition ({}) and provide to ({})'.format(self.condition, self.operation)


class DynamicallyConfiguredOperation(OperationWrapper):
    """
    Wrapper that allows an operation to be initialised with dynamic attributes (e.g. from Context dictionary)
    Provide operation class and args and kwargs to initialise with (values should be callables)
    """
    wrapping_translations = {
        'dataframe': 'dataframe',
        'column': 'column',
        'value': 'value'
    }

    def __init__(self, operation_class, *op_args, **op_kwargs):
        """

        :param operation_class: Operation class
        :param op_args: args to initialise operation with
        :param op_kwargs: kwargs to initialise operation with
        """
        (validate_callable(arg) for arg in op_args)
        (validate_callable(arg) for arg in op_kwargs.values())
        self.op_args = op_args
        self.op_kwargs = op_kwargs
        super().__init__(operation_class)

    def __call__(self, *args, **kwargs):
        # Build operation arguments
        op_arg_values = [op_arg(*args, **kwargs) for op_arg in self.op_args]
        op_kwarg_values = {arg_name: arg_callable(*args, **kwargs) for arg_name, arg_callable in self.op_kwargs.items()}
        # Initialise operation
        operation_instance = self.operation(*op_arg_values, **op_kwarg_values)
        # Call operation
        return operation_instance(*args, **kwargs)

    def __str__(self):
        return '{} with dynamically configured args: {} and kwargs: {}'.format(self.operation.__name__, self.op_args, self.op_kwargs)


class SeriesFromValue(BaseOperation):
    """
    Returns a column/Series of equal constant values, with length equal to that of input DataFrame
    Provided value can be static or callable which returns a value (e.g. from ContextValue)
    """
    calling_translations = {
        'dataframe': 'column',
        'column': 'column',
    }

    def __init__(self, value):
        """

        :param value: static value or callable which returns scalar value
        """
        self.value = value

    def __call__(self, vector):
        """

        :param vector: Dataframe or Series
        :return:
        """
        repeated_value = self.value(vector) if callable(self.value) else self.value
        return pd.Series([repeated_value] * len(vector.index))

    def __str__(self):
        return 'Series with repeated value: {}'.format(self.value)
