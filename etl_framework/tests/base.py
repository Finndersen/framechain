import traceback
import types
from unittest import TestCase
from unittest.case import _AssertRaisesContext

from etl_framework.operations import OperationError


class _AssertRaisesOperationErrorContext(_AssertRaisesContext):
    """A context manager used to implement TestCase.assertRaises* methods."""


    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is None:
            try:
                exc_name = self.expected.__name__
            except AttributeError:
                exc_name = str(self.expected)
            if self.obj_name:
                self._raiseFailure("{} not raised by {}".format(exc_name,
                                                                self.obj_name))
            else:
                self._raiseFailure("{} not raised".format(exc_name))
        else:
            traceback.clear_frames(tb)
        if not (issubclass(exc_type, OperationError) and isinstance(exc_value.wrapped_exception,
                                                                    self.expected)):
            # let unexpected exceptions pass through
            return False
        # store exception, without traceback, for later retrieval
        self.exception = exc_value.with_traceback(None)
        if self.expected_regex is None:
            return True

        expected_regex = self.expected_regex
        if not expected_regex.search(str(exc_value)):
            self._raiseFailure('"{}" does not match "{}"'.format(
                     expected_regex.pattern, str(exc_value)))
        return True

    __class_getitem__ = classmethod(types.GenericAlias)


class ETLFrameworkTestCase(TestCase):

    def assertRaisesOperationError(self, expected_exception, *args, **kwargs):
        """
        Like assertRaises but can provide the underlying exception class wrapped by OperationError
        :return:
        """
        context = _AssertRaisesOperationErrorContext(expected_exception, self)
        try:
            return context.handle('assertRaises', args, kwargs)
        finally:
            # bpo-23890: manually break a reference cycle
            context = None