from etl_framework.operations import profiled, BinaryDurationToInt
from etl_framework.operations.pandas import ColumnToDatetime, ColumnMap, ToNullableInteger
from etl_framework.operations.pandas.record_extractors.base import InputField, IntegerFieldMixin
from etl_framework.operations.transforms import BytesToString, BytesToBoolean, BytesToInteger, BytesToDate, \
    BytesToDateString, BytesToTime, BytesToTimeString, \
    BytesToHexString, TBCDBytesToString, BinaryIPv4AddressToString, BinaryIPv6AddressToString, BCDTimestampToString
from etl_framework.operations.transforms.telephony import ConvertAddressString


class ASN1BERField(InputField):
    """
    Class used to define a BER ASN1 field
    """

    def __init__(self, name, asn_ids, aggregator=None, **kwargs):
        """

        :param str name: name of ASN1 field
        :param dict/str asn_ids: Either:
            - dictionary with keys of recordtype name, and values of str ASN1 id of field within recordtype
            - string of ASN1 Id of field (hyphen-seperated field IDs, applies to all record types)
        :param BaseFieldSetter aggregator: Object which defines logic for how field values are set and aggregated when there
        are multiple (for when field occurs multiple times, e.g. in SEQUENCE OF)
        """
        self.asn_ids = asn_ids
        self.aggregator = aggregator
        super().__init__(name, **kwargs)

    def get_asn_id_for_record_type(self, record_type):
        """
        Get field absolute ASN ID for specific record type
        :param record_type:
        :return:
        """
        relative_field_id = self.asn_ids[record_type.name] if isinstance(self.asn_ids, dict) else self.asn_ids

        return '-'.join([record_type.asn_id, relative_field_id])

    def applicable_to_record_type(self, record_type):
        return isinstance(self.asn_ids, str) or record_type.name in self.asn_ids

    @profiled
    def add_to_record(self, record, raw_value):
        """
        Add new raw field value to record dictionary
        If field already exists in record, will need to aggregate new value with existing
        :param dict record:
        :param raw_value:
        :return:
        """
        # Call self.action() directly for better performance (this method already profiled)
        converted_value = self.action(raw_value)
        # Do not add if None
        if converted_value is None:
            return

        # Set field value value in record
        if self.aggregator:
            self.aggregator.add_to_record(record, self.name, converted_value)
        else:
            record[self.name] = converted_value


class BooleanField(ASN1BERField):
    """
    ASN1 Boolean field
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, value_converter=BytesToBoolean(), **kwargs)


class IntegerField(IntegerFieldMixin, ASN1BERField):
    """
    Bytes to int64. Use for INTEGER ASN1 type
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, value_converter=BytesToInteger(), **kwargs)


class EnumeratedField(IntegerField):
    """
    Field which translates an enumerated integer value to corresponding string value
    """

    def __init__(self, name, asn_id, mapping, **kwargs):
        """

        :param args:
        :param dict mapping: enumeration mapping (of integer values to string representation)
        :param kwargs:
        """
        super().__init__(name, asn_id, column_converter=ColumnMap(mapping), dtype=object, **kwargs)


class StringField(ASN1BERField):
    """
    String field which decodes byte data to string. Use for IA5String or OCTET STRING if appropriate
    """

    def __init__(self, *args, **kwargs):
        # Doesnt appear to be much performance difference between using value or column converter
        super().__init__(*args, value_converter=BytesToString(), dtype=object, **kwargs)


class DateField(ASN1BERField):
    """
    From binary date in 3-byte format YYMMDD to datetime.date or string in YYYY-MM-DD format
    """

    def __init__(self, *args, to_string=False, **kwargs):
        """

        :param args:
        :param bool to_string: Whether to produce date string output instead of date object
        :param kwargs:
        """
        if to_string:
            converter = BytesToDateString()
        else:
            converter = BytesToDate()
        super().__init__(*args, value_converter=converter, **kwargs)


class TimeField(ASN1BERField):
    """
    From binary time in format HHMMSS to datetime.date
    """

    def __init__(self, *args, to_string=False, **kwargs):
        if to_string:
            converter = BytesToTimeString()
        else:
            converter = BytesToTime()
        super().__init__(*args, value_converter=converter, **kwargs)


class DurationField(ASN1BERField):
    """
    From binary time in HHMMSS to total duration in seconds
    """

    def __init__(self, *args, size=32, **kwargs):
        super().__init__(*args,
                         value_converter=BinaryDurationToInt(),
                         column_converter=ToNullableInteger(size=size), **kwargs)


class AddressStringField(ASN1BERField):
    """
    For decoding address strings (usually phone numbers) in format:
    Octet 0: Nature of Address(TON) |   Numbering Plan (NPI)
    Octet 1: Address Digit 2        |   Address digit 1
    ...
    Octet n: Address digit 2n       | Address digit 2n-1

    Address digits need to be nibble-swapped
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         value_converter=ConvertAddressString(),
                         dtype=object, **kwargs)


class OctetStringField(ASN1BERField):
    """
    Convert binary data to hex string representation.
    e.g. b'\x5d\xb1\x80' -> '5DB180'
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         value_converter=BytesToHexString(uppercase=True),
                         dtype=object, **kwargs)


class BCDTimestampField(ASN1BERField):
    """
    From BCD timestamp in format YYMMDDhhmmssShhmm to timezone-aware pd.datetime64
    Chain BCDTimestampToString and StringToDatetime converters
    If timestamp is invalid format, Null value will be returned (instead of raising error)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         value_converter=BCDTimestampToString(),
                         column_converter=ColumnToDatetime(format='%y%m%d%H%M%S%z', errors='coerce'),
                         dtype=object, **kwargs)


class TBCDStringField(ASN1BERField):
    """
    For decoding Telephony Binary Coded Decimal fields to string e.g. MSISDN, IMEI, IMSI
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         value_converter=TBCDBytesToString(),
                         dtype=object, **kwargs)


class IPAddressField(ASN1BERField):
    """
    For decoding binary 4-byte IPv4 or 16-byte IPv6 address to string representation
    """

    def __init__(self, *args, version='ipv4', **kwargs):
        if version == 'ipv4':
            converter = BinaryIPv4AddressToString()
        elif version == 'ipv6':
            converter = BinaryIPv6AddressToString()
        else:
            raise ValueError('IPAddressField version must be "ipv4" or "ipv6"')
        super().__init__(*args, value_converter=converter, dtype=object,
                         **kwargs)


def convert_address_string(bytes_data):
    """
    Convert AddressString (e.g. MSISDN) field as specified in 3GPP TS 29.002
    First octet is for Extension Indication, Nature of Address and NPI:
     -- bit 8: 1 (no extension)
     -- bits 765: nature of address indicator
         -- 000 unknown
         -- 001 international number
         -- 010 national significant number
         -- 011 network specific number
         -- 100 subscriber number
         -- 101 reserved
         -- 110 abbreviated number
         -- 111 reserved for extension
     -- bits 4321: numbering plan indicator
         -- 0000 unknown
         -- 0001 ISDN/Telephony Numbering Plan (Rec CCITT E.164)
         -- 0010 spare
         -- 0011 data numbering plan (CCITT Rec X.121)
         -- 0100 telex numbering plan (CCITT Rec F.69)
         -- 0101 spare
         -- 0110 land mobile numbering plan (CCITT Rec E.212)
         -- 0111 spare
         -- 1000 national numbering plan
         -- 1001 private numbering plan
         -- 1111 reserved for extension
         -- all other values are reserved.
    Remaining octets are encoded as TBCD-STRING (nibble swapped)
    """
    pass


class MSISDNField(ASN1BERField):
    """
    For decoding MSISDN AddressString field (as specified in 3GPP TS 29.002)
    Removes first octet (Extension Indication, Nature of Address and NPI) and nibble-swaps remaining
    Currently only contains validation for ISDN/Telephony international number
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         value_converter=TBCDBytesToString()[2:], **kwargs)
