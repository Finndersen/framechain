import pandas as pd
from etl_framework import exceptions
# from etl_framework.record_extractors.files.asn1 import asn1_decoder_cython
from etl_framework.operations.pandas.record_extractors.asn1_ber import asn1_decoder, ASN1BERField
from etl_framework.operations.pandas.record_extractors.base import BaseDataFrameGenerator
import logging

log = logging.getLogger(__name__)


class ASN1BERRecordExtractor(BaseDataFrameGenerator):
    """
    Record extractor for BER encoded ASN1 files
    Takes binary file content, returns Dataframe of records
    Need to specify record types and fields of interest for extraction
    """
    RECORDTYPE_FIELD_NAME = 'asn1_record_type'

    calling_translations = {'file_data': 'dataframe'}

    def __init__(self, record_types, fields, head_trailer_lengths=None):
        """
        :param list/tuple of ASN1RecordType record_types: ASN1RecordType instances representing target recordtypes
        :param list/tuple of ASN1Field fields: ASN1Field instances describing target fields and ASN1 IDs within target recordtypes
        :param head_trailer_lengths: Mapping which describes format of the ASCII File and Logical header and trailer lines within the ASN1 file.
        """
        # Validate field configuration
        for field in fields:
            # Validate no field has same name as recordtype field name
            if field.name == self.RECORDTYPE_FIELD_NAME:
                self.error(exceptions.ETLConfigurationError, 'ASN1 record schema defined with field name same as recordtype field name: {}'.format(self.RECORDTYPE_FIELD_NAME))

        self.asn_decoder = asn1_decoder.ASN1BERDecoder(record_types, fields, head_trailer_lengths)
        # Add Record Type field so it is not removed during column re-ordering
        super().__init__(fields + [ASN1BERField(self.RECORDTYPE_FIELD_NAME, None)])

    def create_dataframe(self, file_data):
        """
        Create dataframe from input file data
        :param bytes file_data: Binary input data
        :return:
        """
        return pd.DataFrame([record for record in self.get_records(file_data)])

    def get_records(self, file_data):
        """
        Yield ASN1 records extracted from file as dictionaries
        :param bytes file_data: Binary file data
        :return:
        """
        self.asn_decoder.set_asn_data(file_data)
        try:
            while 1:
                # Skip to start of next record
                self.asn_decoder.skip_until_asn_block()
                # Root node = entire record
                record = self.asn_decoder.build_asn_record()
                if record:
                    # Set recordtype name
                    record[self.RECORDTYPE_FIELD_NAME] = self.asn_decoder.current_record_type.name
                    yield record
        except exceptions.EndOfFileError:
            return


