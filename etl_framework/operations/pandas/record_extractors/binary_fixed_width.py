import pandas as pd
from .base import BaseDataFrameGenerator, InputField
from ... import BytesToHexString


class BinaryFixedWidthRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from binary data file with fields defined by byte position and offset, from records with fixed length
    """

    def __init__(self, fields, record_length, record_skip_condition=None):
        """
        :param list fields: List of BFWFields
        :param int record_length: Length of full record line
        :param callable record_skip_condition: Optional callable which takes raw string content of record line and returns boolean whether it should be skipped or not
        """
        super().__init__(fields)
        self.record_length = record_length
        self.record_skip_condition = self.wrap_operation(record_skip_condition)

    def create_dataframe(self, data_file):
        records = []
        # Loop through lines in file
        while True:
            record_data = data_file.read(self.record_length)
            # Detect end of file
            if not record_data:
                break

            # Skip line before extracting field values if necessary
            if self.record_skip_condition and self.run_wrapped_operation(self.record_skip_condition, record_data):
                continue

            # Add record to list
            records.append([field.get_value(record_data) for field in self.fields])
        # Build DataFrame from records and headers
        return pd.DataFrame(records, columns=[field.name for field in self.fields])


class BFWField(InputField):
    """
    Base InputField class for Binary Fixed Width fields
    """
    def __init__(self, name, start_pos, length, **kwargs):
        """

        :param str name: Field name
        :param int start_pos: Byte start position
        :param int length: Byte length
        :param kwargs:
        """
        super().__init__(name, **kwargs)
        self.start_pos = start_pos
        self.length = length
        self.end_pos = start_pos + length  # Pre-compute for performance

    def get_value(self, record):
        """
        Get field value from record
        :param bytes record: Binary record data
        :return:
        """
        return self(record[self.start_pos:self.end_pos])


class HexField(BFWField):
    """
    Field class which converts values to hex representation
    """
    value_converter = BytesToHexString()