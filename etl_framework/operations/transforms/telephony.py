from etl_framework.operations import ScalarOperation


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


class BCDTimestampToString(ScalarOperation):
    """
    Convert BCD timestamp in format YYMMDDhhmmssShhmm to String
    """
    def __call__(self, value):
        return value[:6].hex() + chr(value[6]) + value[7:].hex()


class ConvertCellID(ScalarOperation):
    """
    Convert 14-char hex string representation cell tower identifier (SAI, RAI, CGI or eCGI) to correct format
    MCC and MNC components are out of order and need to be re-arranged
    e.g. '05F51024513D3A' -> '5050124513D3A'
    MCC = '505'
    MNC = '01F' → '01'
    LAC + SAC/RAC/CI = '24513D3A'
    """
    def __init__(self, ecgi=False):
        """

        :param bool ecgi: Whether cell ID is ECGI (will ignore spare digit at position 7)
        """
        self.ecgi = ecgi

    def __call__(self, str_value):
        mcc = str_value[1] + str_value[0] + str_value[3]
        mnc = (str_value[5] + str_value[4] + str_value[2]).rstrip('f')
        return mcc + mnc + str_value[7 if self.ecgi else 6:]


class IPAddressFromHexString(ScalarOperation):
    """
    Convert 8-character hex string to IPv4 address
    E.g. 24513d3a -> 36.81.61.58
    """
    def __call__(self, hex_str):
        return '.'.join(str(int(hex_str[2*i:2*i+2], 16)) for i in range(4))