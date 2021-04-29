from etl_framework.operations.base import Operation, CompoundOperation
from etl_framework.utils import Memoized, validate_callable


class Cached(CompoundOperation):
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
        self.operation = Memoized(operation)
        super().__init__(self.operation)

    def action(self, *args, **kwargs):
        """

        :param args: Transformation primary argument (may not exist if MapFields came first)
        :param kwargs: extra transformation arguments potentially supplied from WithArgs or MapFields
        :return:
        """
        return self.run_wrapped_operation(self.operation, *args, **kwargs)

    def description(self):
        return '({}) with caching'.format(self.operation)


class MapArguments(CompoundOperation):
    """
    Transform wrapper which allows multiple Operation input arguments to be generated from the provided input,
    using specified operation/transform logic for each argument

    """
    wrapping_translations = {
        'dataframe': 'column',
        'row': 'value'
    }
    #
    calling_translations = wrapping_translations

    def __init__(self, operation, **arg_mapping):
        """
        :param operation: Transform or TransformWrapper to supply argument values to
        :param callable, str arg_mapping: mapping of transform arg names to operations which take wrapper input
        and return desired value
        """
        self.arg_mapping = arg_mapping
        self.operation = operation
        super().__init__(self.operation)

    def action(self, *args, **kwargs):
        """

        :param input_val: Value which will be passed to arg_mappings to generate input arguments for operation
        :return:
        """
        return self.run_wrapped_operation(self.operation, **{arg_name: arg_operation(*args, **kwargs)
                                                             for arg_name, arg_operation in self.arg_mapping.items()})

    def description(self):
        return '({}) with arguments: {}'.format(self.operation,
                                                ', '.join(['{}=({})'.format(key,val) for key,val in self.arg_mapping.items()]))


class Not(CompoundOperation):
    """
    Performs Not operator.
    """
    def __init__(self, operation):
        """

        :param operation: Operation to wrap and return NOT result of.
        """
        self.operation = operation
        super().__init__(operation)

    def action(self, *args, **kwargs):
        return not self.run_wrapped_operation(self.operation, *args, **kwargs)

    def description(self):
        return 'NOT ({})'.format(self.operation)


class DynamicallyConfiguredOperation(Operation):
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
        self.operation_class = operation_class

    def action(self, *args, **kwargs):
        # Build operation arguments
        op_arg_values = [op_arg(*args, **kwargs) for op_arg in self.op_args]
        op_kwarg_values = {arg_name: arg_callable(*args, **kwargs) for arg_name, arg_callable in self.op_kwargs.items()}
        # Initialise operation
        operation_instance = self.operation_class(*op_arg_values, **op_kwarg_values)
        # Call operation
        return operation_instance(*args, **kwargs)

    def description(self):
        return '{} with dynamically configured args: {} and kwargs: {}'.format(self.operation.__name__, self.op_args, self.op_kwargs)


