from etl_framework.exceptions import *


class ASNDecodeError(ETLError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class SkipRecordError(Exception):
    """
    Exception for skipping entire root-level ASN1 record
    """
    pass


class MultipleValueError(ASNDecodeError):
    """
    Error for when multiple ASN1 field values encountered but no aggregator defined
    """
    pass