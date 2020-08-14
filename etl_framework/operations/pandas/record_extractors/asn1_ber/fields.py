from etl_framework.operations.pandas.transforms import StringColumnToDatetime
from etl_framework.operations.transforms.binary import BytesToString, BytesToBoolean, BytesToInteger, BytesToDate, BytesToDateString, BytesToTime, BytesToTimeString, \
    BytesToHexString
from etl_framework.operations.transforms import TBCDBytesToString, BinaryToIPv4Address, BinaryToIPv6Address, \
    BCDTimestampToString
from etl_framework.operations.pandas.record_extractors.base import InputField, IntegerFieldMixin
from etl_framework.exceptions import ETLFieldError, ValidationError


class ASN1BERField(InputField):
    """
    Class used to define a BER ASN1 field
    """
    def __init__(self, name, asn_ids, **kwargs):
        """

        :param str name: name of ASN1 field
        :param dict/str asn_ids: Either:
            - dictionary with keys of recordtype name, and values of str ASN1 id of field within recordtype
            - string of ASN1 Id of field (hyphen-seperated field IDs, applies to all record types)
        """
        self.asn_ids = asn_ids
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

    def aggregate_values(self, existing_value, new_value):
        """
        Logic for aggregating multiple values of a field that occurs multiple times in a record (if with SEQUENCE OF
        or SET OF construct)
        :param existing_value: Existing aggregated field value
        :param new_value: New field value
        :return:
        """
        raise ETLFieldError('{} does not support duplicate values in record'.format(self.name))


class BooleanField(ASN1BERField):
    """
    ASN1 Boolean field
    """
    value_converter = BytesToBoolean()


class IntegerField(IntegerFieldMixin, ASN1BERField):
    """
    Bytes to int64. Use for INTEGER or ENUMERATED ASN1 type
    """
    value_converter = BytesToInteger()

    def aggregate_values(self, existing_value, new_value):
        return existing_value + new_value


class StringField(ASN1BERField):
    """
    String field which decodes byte data to string. Use for IA5String or OCTET STRING if appropriate
    """
    value_converter = BytesToString()


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


class BCDField(ASN1BERField):
    """
    Read binary data as Binary-Coded-Decimal
    """
    value_converter = BytesToHexString()


class BCDTimestampField(ASN1BERField):
    """
    From BCD timestamp in format YYMMDDhhmmssShhmm to timezone-aware pd.datetime64
    Chain BCDTimestampToString and StringToDatetime converters
    TODO: Check if its faster to do Scalar or Vector converter for string to datetime?
    """
    value_converter = BCDTimestampToString()
    column_converter = StringColumnToDatetime(format='%y%m%d%H%M%S%z')


class TBCDField(ASN1BERField):
    """
    For decoding Telephony Binary Coded Decimal fields e.g. MSISDN, IMEI, IMSI
    """
    #column_converter = Apply(binary.TBCDParser())
    value_converter = TBCDBytesToString()


class IPAddressField(ASN1BERField):
    """
    For decoding binary 4-byte IPv4 or 16-byte IPv6 address to string representation
    """
    def __init__(self, *args, version='ipv4', **kwargs):
        if version == 'ipv4':
            converter = BinaryToIPv4Address()
        elif version == 'ipv6':
            converter = BinaryToIPv6Address()
        else:
            raise ValueError('IPAddressField version must be "ipv4" or "ipv6"')
        super().__init__(*args, value_converter=converter, **kwargs)


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

    value_converter = TBCDBytesToString()[2:]

    def validate_raw_value(self, value):
        # Ensure Extension Indication, Nature of Address and NPI is ISDN/Telephony international number
        if value[0:2] != b'\x91\x16':
            raise ValidationError('Unexpected number format for MSISDN: {}'.format(value))


