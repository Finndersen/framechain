import functools
import logging, time
# from .operations import Value
from .exceptions import ETLConfigurationError
import random, string


class LogDuration(object):
    """
    Wrapper class for timing and logging duration of activity
    """
    indent = 0

    def __init__(self, logger, message, level=logging.DEBUG):
        self.logger = logger
        self.level = level
        self.logger.log(self.level, '\t'*LogDuration.indent + message)
        LogDuration.indent += 1
        self.start_time = time.perf_counter()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        LogDuration.indent -= 1
        self.logger.log(self.level, '{}Duration: {:.05f}'.format('\t'*LogDuration.indent, time.perf_counter() - self.start_time))


class Memoized(object):
    """
    Decorator. Caches a function's return value each time it is called.
    If called later with the same arguments, the cached value is returned
    (not reevaluated).
    """

    def __init__(self, func):
        self.func = func
        self.cache = {}

    def __call__(self, *args, **kwargs):
        key = (args, frozenset(kwargs.items()))
        if key not in self.cache:
            self.cache[key] = self.func(*args, **kwargs)
        return self.cache[key]

    def __repr__(self):
        """Return the function's docstring."""
        return self.func.__doc__

    def __get__(self, obj, objtype):
        """Support instance methods."""
        return functools.partial(self.__call__, obj)


def validate_callable(op, optional=True, wrap_scalar=True):
    """
    Validates whether provided object is callable. if not, wraps scalar value in Value() operation to make it callable
    If value is basic scalar, wrap with Value() operation
    :param op:
    :param bool optional: Whether func is allowed to be None
    :param bool wrap_scalar: Whether to wrap non-callable value in Value() operation
    :return:
    """
    if optional and op is None:
        return None
    if callable(op):
        return op
    # if wrap_scalar:
    #     return Value(op)

    raise ETLConfigurationError('Provided operation is not callable: {}'.format(op))


class ConfigurableClass(object):
    """
    Base class which contains helpers for validating configuration
    """
    # List of attributes which must be defined (cannot be None)
    MANDATORY_PARAMS = []

    def __init__(self):
        for param in self.MANDATORY_PARAMS:
            if getattr(self, param, None) is None:
                self.configuration_error('Config parameter: {} is not defined'.format(param))

        self.validate_configuration()

    def validate_configuration(self):
        """
        Perform extra custom configuration validation
        :return:
        """
        pass

    def configuration_error(self, message):
        raise ETLConfigurationError('{}: {}'.format(type(self).__name__, message))


def randomstring(length):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))