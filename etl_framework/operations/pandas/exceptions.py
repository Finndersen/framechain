from etl_framework.exceptions import ETLError

class MaskMismatchError(ETLError):
    """
    Error for incorrect boolean mask when integrating data into series
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