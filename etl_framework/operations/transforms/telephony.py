from etl_framework.operations import Operation


class TBCDBytesToString(Operation):
    """
    Convert binary number in Telephony Binary Coded Decimal nibble-swapped format to text string
    This is a format often used to represent MSISDN, IMSI, IMEI numbers in ASN1 encoded data
    e.g. b'\x53\x46\x00\x80\x50\x57\x51\xf0' -> '356400080575150'
    """

    def action(self, value):
        """

        :param bytes value: Nibble-swapped BCD byte value
        :return:
        """
        # Nibble swap each octet and convert to hex string
        hex_str = bytes((((x & 0x0F) << 4) + (x >> 4)) for x in value).hex().upper()
        # Strip Trailing 'f' blank character (slightly faster than rstrip('f'))
        if hex_str[-1] == 'F':
            hex_str = hex_str[:-1]
        return hex_str


class StringToTBCDBytes(Operation):
    """
    Convert string value (containing only 0-F) to TBCDBytes format
    Append trailing 'f' if odd length, convert to bytes, nibble swap
    Inverse of TBCDBytesToString
    e.g. '505013485571338' -> b'\x05\x05\x31\x84\x55\x17\x33\xf8'
    """
    def action(self, value):
        """

        :param str value: String value
        :return: bytes
        """
        if len(value) % 2:
            value += 'f'
        return bytes((((x & 0x0F) << 4) + (x >> 4)) for x in bytes.fromhex(value))


class ConvertAddressString(Operation):
    """
    Preserve first byte (TON and NPI), nibble swap remaining (address)
    :return:
    """
    def __init__(self):
        super().__init__()
        self.tbcd_converter = self.add_child_operation(TBCDBytesToString())

    def action(self, binary_value):
        return binary_value[0:1].hex() + self.tbcd_converter(binary_value[1:])


class BinaryIPv4AddressToString(Operation):
    """
    Convert IPv4 address in binary format (4 bytes, each representing one address segment) to XXX.XXX.XXX.XXX format
    b'\x0a\x3c\x35\x03' -> '10.60.53.3'
    """
    def action(self, byte_str):
        """

        :param bytes byte_str: Binary iPv4 address
        :return:
        """
        return '{}.{}.{}.{}'.format(byte_str[0], byte_str[1], byte_str[2], byte_str[3])


class IPv4AddressStringToBinary(Operation):
    """
    Convert IPv4 Address string to binary
    '10.60.53.3' -> b'\x0a\x3c\x35\x03'
    """
    def action(self, ipv4_str):
        """

        :param str ipv4_str:
        :return:
        """
        return bytes(int(val) for val in ipv4_str.split('.'))


class BinaryIPv6AddressToString(Operation):
    """
    Convert IPv6 address in Binary format (8x pairs of bytes) to string
    b'\x20\x01\x0d\xb8\x00\x01\x00\x00\x00\x00\x0a\xb9\xc0\xa8\x01\x02' -> '2001:0db8:0001:0000:0000:0ab9:C0A8:0102'
    """
    def action(self, value):
        """

        :param bytes value: Binary IPv6 address
        :return:
        """
        hex_str = value.hex()
        return ':'.join([hex_str[i * 4:(i * 4) + 4] for i in range(8)])


class IPv6AddressStringToBinary(Operation):
    """
    Convert IPv6 Address string to binary
    '2001:0db8:0001:0000:0000:0ab9:C0A8:0102' -> b'\x20\x01\x0d\xb8\x00\x01\x00\x00\x00\x00\x0a\xb9\xc0\xa8\x01\x02'
    """
    def action(self, ipv6_str):
        """

        :param str ipv6_str:
        :return:
        """
        return bytes.fromhex(''.join(ipv6_str.split(':')))


class BCDTimestampToString(Operation):
    """
    Convert binary BCD timestamp in format YYMMDDhhmmssShhmm to String
    The UTC offset sign (+ or -) is encoded as ASCII value while rest are BCD
    """
    def action(self, value):
        return value[:6].hex() + chr(value[6]) + value[7:].hex()


class ConvertCellID(Operation):
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
        super().__init__()
        self.ecgi = ecgi

    def action(self, str_value):
        # Handle case of error single byte value
        if len(str_value) <= 2:
            return None
        mcc = str_value[1] + str_value[0] + str_value[3]
        mnc = (str_value[5] + str_value[4] + str_value[2]).rstrip('F')
        return mcc + mnc + str_value[7 if self.ecgi else 6:]


class IPAddressFromHexString(Operation):
    """
    Convert 8-character hex string to IPv4 address
    E.g. 24513d3a -> 36.81.61.58
    """
    def action(self, hex_str):
        return '.'.join(str(int(hex_str[2*i:2*i+2], 16)) for i in range(4))

