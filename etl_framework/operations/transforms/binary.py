"""
Operations which do conversions to or from binary data (bytes)
"""
from datetime import date, time
from etl_framework.operations import Operation


class BytesToString(Operation):
    """
    Decode byte value to string
    """
    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    def action(self, byte_str):
        return byte_str.decode(self.encoding)


class StringToBytes(Operation):
    """
    Encode string value to Bytes
    """
    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    def action(self, string):
        return string.encode(encoding=self.encoding)


class BytesToBoolean(Operation):
    """
    Convert byte value to boolean.
    """
    def action(self, byte):
        return byte > b'\x00'


class BytesToInteger(Operation):
    """
    Convert bytes to integer
    """
    def __init__(self, byteorder='big', signed=False):
        self.byteorder = byteorder
        self.signed = signed

    def action(self, value):
        return int.from_bytes(value, byteorder=self.byteorder, signed=self.signed)


class BytesToHexString(Operation):
    """
    Convert bytes to BCD hex string
    Effectively gets binary representation of integer and breaks it into 4-bit blocks
    e.g. b'\x05\x05\x01`\x01\x11I@' -> '505016001114940'
    """

    def __init__(self, hex_length=None):
        """

        :param int hex_length: Expected length of output hex string. If specified and output is longer, leading zeros will be removed
        """
        self.hex_length = hex_length

    def action(self, value):
        # Trim off '0x' from start of string
        hex_str = value.hex()
        # 0-pad hex string if required
        if self.hex_length:
            hex_str = hex_str[-self.hex_length:]

        return hex_str


class IntegerToBytes(Operation):
    """
    Convert integer value to bytes string
    """
    def __init__(self, bytes_length):
        """

        :param bytes_length: Length of output bytes string
        """
        self.bytes_length = bytes_length

    def action(self, int_value):
        return int_value.to_bytes(self.bytes_length, byteorder='big')


class BinaryDurationToInt(Operation):
    """
    Convert duration in 3-byte binary format to single integer value.
    raw values should consist of 3 byte values, corresponding to duration in format hours, minutes and seconds
    Scalar version
    """
    def action(self, byte_val):
        return byte_val[0] * 3600 + byte_val[1] * 60 + byte_val[2]


#########################################
# Telephone-related Binary data conversions
#########################################


class BytesToDate(Operation):
    """
    Convert date in binary format (YYMMDD) to python date object
    Input value should be byte string of length 3.
    Byte 1: Year after 2000
    Byte 2: month
    BYte 3: Day
    """
    def action(self, value):
        return date(2000 + value[0], value[1], value[2])


class BytesToDateString(Operation):
    """
    Convert date in binary format to date string in format YYYY-MM-DD
    Input value should be byte string of length 3.
    Byte 1: Year after 2000
    Byte 2: month
    BYte 3: Day
    """

    def action(self, value):
        return '{}-{:02}-{:02}'.format(2000 + value[0], value[1], value[2])


class BytesToTime(Operation):
    """
    Convert time in binary format (HHMMSS) to python time object
    Input value should be byte string of length 3.
    Byte 1: Hour
    Byte 2: Minute
    BYte 3: Second
    """
    def action(self, raw_value):
        return time(raw_value[0], raw_value[1], raw_value[2])


class BytesToTimeString(Operation):
    """
    Convert time in binary format to time string in format HH:MM:SS
    Input value should be byte string of length 3.
    Byte 1: Hour
    Byte 2: Minute
    BYte 3: Second
    """
    def action(self, raw_value):
        return '{:02}:{:02}:{:02}'.format(raw_value[0], raw_value[1], raw_value[2])


