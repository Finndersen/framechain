import functools
import itertools
import logging
import random
import string
import time
from datetime import timedelta, tzinfo

import pytz
from pytz.tzinfo import StaticTzInfo, BaseTzInfo

from .exceptions import ETLConfigurationError


class LogDuration(object):
    """
    Wrapper class for timing and logging duration of activity
    """
    indent = 0

    def __init__(self, logger, message, level=logging.DEBUG):
        self.logger = logger
        self.level = level
        self.logger.log(self.level, '\t' * LogDuration.indent + message)
        LogDuration.indent += 1
        self.start_time = time.perf_counter()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        LogDuration.indent -= 1
        self.logger.log(self.level,
                        '{}Duration: {:.05f}'.format('\t' * LogDuration.indent, time.perf_counter() - self.start_time))


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

    def __getattr__(self, item):
        return getattr(self.func, item)


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


def convert_timezone(tz, allow_none=False):
    """
    Convert a timezone represented in various formats to tzinfo instance which is a subclass of pytz.BaseTzInfo
    (which has .localize() method so dont need to differentiate between static vs dynamic UTC offset timezones)
    Can be supplied as either:
    - Timezone name as string
    - UTC Offset in seconds as integer
    - UTC offset as timedelta
    - tzinfo instance (datetime.timezone, pytz.timezone, dateutil.tz.tz.tzoffset etc)
    :param tz:
    :param allow_none: Whether None value is allowed to be provided and passed through
    :return:
    """
    if tz is None and allow_none:
        return None

    if isinstance(tz, str):
        # Construct from timezone string
        tz = pytz.timezone(tz)

    elif isinstance(tz, int):
        # Construct static-offset timezone from UTC Offset in seconds
        tz = StaticOffsetTz(timedelta(seconds=tz))

    elif isinstance(tz, timedelta):
        tz = StaticOffsetTz(tz)

    if isinstance(tz, BaseTzInfo):
        # Is subclass of BaseTzInfo so has .localize() method as desired
        return tz

    if isinstance(tz, tzinfo):
        # Construct StaticTz instance from other tzinfo type (e.g. datetime.timezone, dateutil.tz.tz.tzinfo)
        return StaticOffsetTz(tz.utcoffset(None), name=tz.tzname(None))

    raise TypeError('Invalid timezone value: {}'.format(tz))


def StaticOffsetTz(utcoffset, name=None):
    """
    Get a tzinfo instance with static offset from UTC
    Need to dynamically construct the class instead of initialising instance with parameters because:
    "Special requirement for pickling: A tzinfo subclass must have an __init__() method that can be called with no
    arguments, otherwise it can be pickled but possibly not unpickled again"

    :param utcoffset:
    :param name:
    :return:
    """
    if not isinstance(utcoffset, timedelta):
        raise TypeError('UTC Offset must be timedelta, not: {}'.format(utcoffset))

    name = name or _name_from_offset(utcoffset)
    cls = type(name, (StaticTzInfo,), dict(
        zone=name,
        _utcoffset=utcoffset,
        _tzname=name))
    return cls()


def _name_from_offset(delta):
    if delta < timedelta(0):
        sign = '-'
        delta = -delta
    else:
        sign = '+'
    hours, rest = divmod(delta, timedelta(hours=1))
    minutes = rest // timedelta(minutes=1)
    return 'UTC{}{:02d}:{:02d}'.format(sign, hours, minutes)


def chunks(iterator, n):
    """
    Split an iterator into chunks of length n
    :param iterator:
    :param int n: Chunk size (or None to skip chunking)
    :return:
    """
    # return single chunk if None
    if n is None:
        for chunk in [iterator]:
            yield chunk
    else:
        for first in iterator:  # take one item out (exits loop if `iterator` is empty)
            rest_of_chunk = itertools.islice(iterator, 0, n - 1)
            yield itertools.chain([first], rest_of_chunk)  # concatenate the first item back

