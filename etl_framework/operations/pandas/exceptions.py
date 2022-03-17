from etl_framework.exceptions import *


class MaskMismatchError(ETLError):
    """
    Error for incorrect boolean mask when integrating data into series
    """
    pass


class LengthMismatchError(ETLError):
    """
    Error for when there is a mismatch in array length (Series or DF)
    """
    pass


class ChangedDataTypeError(ETLError):
    """
    Error for when operation changes datatype in masked transformation
    """
    pass


class DTypeError(TypeError, ETLError):
    """
    Error for mismatching padnas datatype
    """
    pass


class InvalidColumnError(ETLError):
    """
    Error for when expected column is missing in DF
    """
    pass
