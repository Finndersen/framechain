import logging

import pandas as pd

from etl_framework.exceptions import ETLConfigurationError, EndOfFileError
from etl_framework.operations.pandas.record_extractors.asn1_ber import ASN1BERDecoder, ASN1BERField
from etl_framework.operations.pandas.record_extractors.base import BaseDataFrameGenerator

log = logging.getLogger(__name__)


class ASN1BERRecordExtractor(BaseDataFrameGenerator):
    """
    Record extractor for BER encoded ASN1 files
    Takes binary file content, returns Dataframe of records
    Need to specify record types and fields of interest for extraction
    """

    calling_translations = {'file_data': 'dataframe'}

    def __init__(self, record_types, fields, data_skipper=None, record_processor=None, **kwargs):
        """
        :param list/tuple of ASN1RecordType record_types: ASN1RecordType instances representing target recordtypes
        :param list/tuple of ASN1Field fields: ASN1Field instances describing target fields and ASN1 IDs within target recordtypes
        :param data_skipper: function used to skip header/trailer/filler data before an ASN1 record. Takes record data and current index, returns new index
        :param record_processor: Optional callable used to process each record dictionary before being provided to DataFrame initialisation
        """
        super().__init__(fields, **kwargs)
        # Validate no field has same name as recordtype field name
        for field in fields:
            if field.name == self.RECORDNUMBER_FIELD_NAME:
                raise ETLConfigurationError(
                    'ASN1 record schema defined with field name same as recordtype number name: {}'.format(
                        self.RECORDNUMBER_FIELD_NAME))
        self.asn_decoder = ASN1BERDecoder(record_types, fields, data_skipper,
                                          record_type_field_name=self.RECORDTYPE_FIELD_NAME)

        self.record_processor = self.wrap_operation(record_processor, none_allowed=True)

    def create_dataframe(self, file_data):
        """
        Create dataframe from input file data
        :param bytes file_data: Binary input data or file reader object
        :return:
        """
        if not isinstance(file_data, bytes):
            if hasattr(file_data, 'read'):
                file_data = file_data.read()
            else:
                raise ValueError('Expected bytes data or file reader object, not {}'.format(type(file_data)))
        df = pd.DataFrame([self.run_wrapped_operation(self.record_processor, record)
                           if self.record_processor else record
                           for record in self.get_records(file_data)])
        return df

    def get_records(self, file_data):
        """
        Yield ASN1 records extracted from file as dictionaries
        :param bytes file_data: Binary file data
        :return:
        """
        self.asn_decoder.set_asn_data(file_data)
        try:
            record_number = 1
            while 1:
                # Skip to start of next record
                self.asn_decoder.skip_until_asn_block()
                # Root node = entire record
                record = self.asn_decoder.decode_asn_record()
                if record:
                    record[self.RECORDNUMBER_FIELD_NAME] = record_number
                    yield record
                record_number += 1
        except EndOfFileError:
            return

    def order_fields(self, dataframe):
        # Create ordered list of columns
        # Record type and number + defined fields
        expected_columns = ([self.RECORDTYPE_FIELD_NAME, self.RECORDNUMBER_FIELD_NAME] +
                            [field.name for field in self.fields if field.name in dataframe.columns])
        # Any other fields added (perhaps by record processor)
        extra_colums = [column for column in dataframe.columns if column not in expected_columns]
        dataframe = dataframe[expected_columns + extra_colums]
        return dataframe
