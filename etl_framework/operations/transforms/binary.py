"""
Operations which do conversions to or from binary data (bytes)
"""
from datetime import date, time
from etl_framework.operations import ScalarOperation


class BytesToString(ScalarOperation):
    """
    Decode byte value to string
    """
    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    def __call__(self, byte_str):
        return byte_str.decode(self.encoding)


class StringToBytes(ScalarOperation):
    """
    Encode string value to Bytes
    """
    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    def __call__(self, string):
        return string.encode(encoding=self.encoding)


class BytesToBoolean(ScalarOperation):
    """
    Convert byte value to boolean.
    """
    def __call__(self, byte):
        return byte > b'\x00'


class BytesToInteger(ScalarOperation):
    """
    Convert bytes to integer
    """
    def __init__(self, byteorder='big', signed=False):
        self.byteorder = byteorder
        self.signed = signed

    def __call__(self, value):
        return int.from_bytes(value, byteorder=self.byteorder, signed=self.signed)


class BytesToHexString(ScalarOperation):
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

    def __call__(self, value):
        # Trim off '0x' from start of string
        hex_str = value.hex()
        # 0-pad hex string if required
        if self.hex_length:
            hex_str = hex_str[-self.hex_length:]

        return hex_str


class IntegerToBytes(ScalarOperation):
    """
    Convert integer value to bytes string
    """
    def __init__(self, bytes_length):
        """

        :param bytes_length: Length of output bytes string
        """
        self.bytes_length = bytes_length

    def __call__(self, int_value):
        return int_value.to_bytes(self.bytes_length, byteorder='big')


class IntToHexString(ScalarOperation):
    """
    Convert integer to BCD hex string
    Effectively gets binary representation of integer and breaks it into 4-bit blocks
    e.g. 361696856919591232 -> '505016001114940'
    """
    def __init__(self, hex_length=None):
        """

        :param int hex_length: Expected length of output hex string. If specified and output is shorter, will be zero-padded as required
        """
        self.hex_length = hex_length

    def __call__(self, value):
        # Trim off '0x' from start of string
        hex_str = hex(value)[2:]
        # 0-pad hex string if required
        if self.hex_length and len(hex_str) < self.hex_length:
            hex_str = hex_str.zfill(self.hex_length)

        return hex_str


class BinaryDurationToInt(ScalarOperation):
    """
    Convert duration in 3-byte binary format to single integer value.
    raw values should consist of 3 byte values, corresponding to duration in format hours, minutes and seconds
    Scalar version
    """
    def __call__(self, byte_val):
        return byte_val[0] * 3600 + byte_val[1] * 60 + byte_val[2]


class TBCDBytesToString(ScalarOperation):
    """
    Convert binary number in Telephony Binary Coded Decimal nibble-swapped format to text string
    This is a format often used to represent MSISDN, IMSI, IMEI numbers in ASN1 encoded data
    """

    def __call__(self, value):
        # Nibble swap each octet and convert to hex string
        hex_str = bytes((((x & 0x0F) << 4) + (x >> 4)) for x in value).hex()
        # Strip Trailing 'f'
        if hex_str[-1] == 'f':
            hex_str = hex_str[:-1]
        return hex_str


class BinaryToIPv4Address(ScalarOperation):
    """
    Convert IPv4 address in binary format (4 bytes, each representing one address segment) to XXX.XXX.XXX.XXX format
    """
    def __call__(self, byte_str):
        return '{}.{}.{}.{}'.format(byte_str[0], byte_str[1], byte_str[2], byte_str[3])


class BinaryToIPv6Address(ScalarOperation):
    """
    Convert IPv6 address in Binary format (8x pairs of bytes) to string
    COULD PROBABLY BE VECTORISED IF REQUIRED
    """
    def __call__(self, value):
        hex_str = value.hex()
        return ':'.join([hex_str[i * 4:(i * 4) + 4] for i in range(8)])


class BytesToDate(ScalarOperation):
    """
    Convert date in binary format to python date object
    Input value should be byte string of length 3.
    Byte 1: Year after 2000
    Byte 2: month
    BYte 3: Day
    """
    def __call__(self, value):
        return date(2000 + value[0], value[1], value[2])


class BytesToDateString(ScalarOperation):
    """
    Convert date in binary format to date string in format YYYY-MM-DD
        Input value should be byte string of length 3.
    Byte 1: Year after 2000
    Byte 2: month
    BYte 3: Day
    """

    def __call__(self, value):
        return '{}-{:02}-{:02}'.format(2000 + value[0], value[1], value[2])


class BytesToTime(ScalarOperation):
    """
    Convert time in binary format to python time object
    Input value should be byte string of length 3.
    Byte 1: Hour
    Byte 2: Minute
    BYte 3: Second
    """
    def __call__(self, raw_value):
        return time(raw_value[0], raw_value[1], raw_value[2])


class BytesToTimeString(ScalarOperation):
    """
    Convert time in binary format to time string in format HH:MM:SS
    Input value should be byte string of length 3.
    Byte 1: Hour
    Byte 2: Minute
    BYte 3: Second
    """
    def __call__(self, raw_value):
        return '{:02}:{:02}:{:02}'.format(raw_value[0], raw_value[1], raw_value[2])


class BCDTimestampToString(ScalarOperation):
    """
    Convert BCD timestamp in format YYMMDDhhmmssShhmm to String
    """
    def __call__(self, value):
        return value[:6].hex() + chr(value[6]) + value[7:].hex()