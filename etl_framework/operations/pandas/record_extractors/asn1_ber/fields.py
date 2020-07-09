from etl_framework.operations.pandas.transforms import StringColumnToDatetime
from etl_framework.operations.transforms.binary import BytesToString, BytesToBoolean, BytesToInteger, TBCDBytesToString, \
    BinaryToIPv4Address, BinaryToIPv6Address, BytesToDate, BytesToDateString, BytesToTime, BytesToTimeString, \
    BCDTimestampToString
from etl_framework.operations.pandas.record_extractors.base import InputField, IntegerFieldMixin
from etl_framework.operations.pandas.record_extractors.asn1_ber.asn1_decoder import ASN1BERRecordField
from etl_framework.exceptions import ETLConfigurationError


class ASN1BERField(InputField):
    """
    Object used to define a BER ASN1 field
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

    def get_recordtype_field(self, recordtype_name):
        """
        Get corresponding ASN1RecordField for this ASN1 field definition and record type
        :param str recordtype_name:
        :return:
        """
        return ASN1BERRecordField(name=self.name,
                                  tag=self.asn_ids[recordtype_name] if isinstance(self.asn_ids, dict) else self.asn_ids,
                                  converter=self.value_converter)


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


class StringField(ASN1BERField):
    """
    String field which decodes byte data to string. Use for IA5String or OCTET STRING if appropriate
    """
    value_converter = BytesToString()


class DateField(ASN1BERField):
    """
    From binary date in 3-byte format YYMMDD to datetime.date or string in YYYY-MM-DD format
    """
    def __init__(self, *args, output_type='date', **kwargs):
        if output_type == 'date':
            converter = BytesToDate()
        elif output_type == 'string':
            converter = BytesToDateString()
        else:
            raise ETLConfigurationError('DateField output_type must be "date" or "string"')
        super().__init__(*args, value_converter=converter, **kwargs)


class TimeField(ASN1BERField):
    """
    From binary time in format HHMMSS to datetime.date
    """
    def __init__(self, *args, output_type='time', **kwargs):
        if output_type == 'time':
            converter = BytesToTime()
        elif output_type == 'string':
            converter = BytesToTimeString()
        else:
            raise ETLConfigurationError('TimeField output_type must be "time" or "string"')
        super().__init__(*args, value_converter=converter, **kwargs)


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
            raise ETLConfigurationError('IPAddressField version must be "ipv4" or "ipv6"')
        super().__init__(*args, value_converter=converter, **kwargs)