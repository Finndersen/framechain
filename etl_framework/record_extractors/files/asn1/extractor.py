import pandas as pd
from etl_framework import exceptions
# from etl_framework.record_extractors.files.asn1 import asn1_decoder_cython
from etl_framework.record_extractors.files.asn1 import asn1_decoder
from etl_framework.record_extractors.files.base import FileRecordExtractor
import logging

log = logging.getLogger(__name__)


class ASN1RecordExtractor(FileRecordExtractor):
    """
    Decode ASN1 files target specific tag sets
    """
    RECORDTYPE_FIELD_NAME = 'asn1_record_type'

    def __init__(self, file_reader, record_types, fields, head_trailer_lengths):
        """
        :param file_reader: callable to take file path and returned opened file object
        :param list/tuple of ASN1RecordType record_types: ASN1RecordType instances representing target recordtypes
        :param list/tuple of ASN1Field fields: ASN1Field instances describing target fields and ASN1 IDs within target recordtypes
        :param head_trailer_lengths: Mapping which describes format of the ASCII File and Logical header and trailer lines within the ASN1 file.
        """
        # Validate field configuration
        record_type_names = {record_type.name for record_type in record_types}
        for field in fields:
            # Validate no field has same name as recordtype field name
            if field.name == self.RECORDTYPE_FIELD_NAME:
                raise exceptions.ETLConfigurationError('ASN1 record schema defined with field name same as recordtype field name: {}'.format(self.RECORDTYPE_FIELD_NAME))
            # Validate all field mappings use defined recordtype
            if isinstance(field.asn_ids, dict):
                for record_type_name in field.asn_ids:
                    if record_type_name not in record_type_names:
                        raise exceptions.ETLConfigurationError('Record Type {} defined in {} configuration is invalid'.format(record_type_name, field))

        # Build ASN1RecordSchema instances from record type and field definitions
        record_schemas = []
        for record_type in record_types:
            # Build field definition for record type
            record_type_fields = tuple(field.get_recordtype_field(record_type.name)
                               for field in fields
                               if isinstance(field.asn_ids, str) or (record_type.name in field.asn_ids))
            record_schema = asn1_decoder.ASN1RecordSchema(record_type.name, record_type.asn_id, record_type_fields)
            record_schemas.append(record_schema)

        self.asn_decoder = asn1_decoder.Asn1Decoder(record_schemas, head_trailer_lengths)
        super().__init__(file_reader, fields)

    def dataframe_from_file(self, data_file):
        return pd.DataFrame([record for record in self.get_records(data_file)])

    def get_records(self, data_file):
        """
        Yield ASN1 records extracted from file as dictionaries
        :param data_file:
        :return:
        """
        self.asn_decoder.set_asn_data(data_file.read())
        try:
            while 1:
                # Skip to start of next record
                self.asn_decoder.skip_until_asn_block()
                # Root node = entire record
                root_node = self.asn_decoder.decode_node(None)
                record = self.asn_decoder.build_asn_record(root_node)
                if record:
                    # Set recordtype name
                    record[self.RECORDTYPE_FIELD_NAME] = self.asn_decoder.current_record_schema.recordtype_name
                    yield record
        except exceptions.EndOfFileError:
            return


class ASN1RecordType(object):
    """
    Simple object to define an ASN1 record type
    """
    def __init__(self, name, asn_id):
        """
        :param str name: name of record type
        :param str asn_id: constructed node ASN1 ID of record type (string of hyphen-seperated integers)
        """
        self.name = name
        self.asn_id = asn_id
