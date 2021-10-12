from etl_framework.operations import Operation
from etl_framework.utils import Memoized


class Cached(Operation):
    """
    Transform wrapper which enables caching of output values
    Should wrap actual transform directly (not another TransformWrapper)
    Only compatible with Scalar (value) transforms
    """

    def __init__(self, operation):
        super().__init__()
        self.operation = Memoized(self.add_child_operation(operation, wrap_value=False))

    def action(self, *args):
        """

        :param args: Transformation primary argument
        :return:
        """
        return self.run_child_operation(self.operation, *args)

    def description(self):
        return '({}) with caching'.format(self.operation)


class MapArguments(Operation):
    """
    Transform wrapper which allows multiple Operation input arguments to be generated from the provided input,
    using specified operation/transform logic for each argument

    """

    def __init__(self, operation, **arg_mapping):
        """
        :param operation: Transform or TransformWrapper to supply argument values to
        :param callable, str arg_mapping: mapping of transform arg names to operations which take wrapper input
        and return desired value
        """
        super().__init__()
        self.arg_mapping = {arg_name: self.add_child_operation(op) for arg_name, op in arg_mapping.items()}
        self.operation = self.add_child_operation(operation)

    def action(self, *args):
        """

        :param args: Values which will be passed to arg_mappings to generate input arguments for operation
        :return:
        """
        return self.run_child_operation(self.operation, **{arg_name: arg_operation(*args)
                                                           for arg_name, arg_operation in self.arg_mapping.items()})

    def description(self):
        return '({}) with arguments: {}'.format(self.operation,
                                                ', '.join(['{}=({})'.format(key,val) for key,val in self.arg_mapping.items()]))


class DynamicallyConfiguredOperation(Operation):
    """
    Wrapper that allows an operation to be initialised with dynamic attributes (e.g. from Context dictionary)
    Provide operation class and args and kwargs to initialise with (values should be callables)
    """

    def __init__(self, operation_class, *op_args, **op_kwargs):
        """

        :param operation_class: Operation class
        :param op_args: args to initialise operation with
        :param op_kwargs: kwargs to initialise operation with
        """
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


