import pandas as pd
from etl_framework.operations import BytesToString, profiled

from .base import BaseDataFrameGenerator, InputField
from etl_framework.operations.transforms import BytesToHexString, BytesToInteger
from etl_framework.operations.pandas import ToInteger


class BinaryFixedWidthRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from binary data file with fields defined by byte position and offset, from records with fixed length
    Can provide recordtype_detector which takes raw record data and returns record type, or None if record should be skipped
    """

    def __init__(self, fields, record_length, recordtype_detector=None, record_processor=None, **kwargs):
        """
        :param list fields: List of BFWFields
        :param int record_length: Length of full record line
        :param recordtype_detector: Optional callable which takes raw content of record line and returns
        record type as string, or None if record should be skipped
        :param record_processor: Optional callable to process record dictionary before constructing dataframe
        """
        super().__init__(fields, **kwargs)
        self.record_length = record_length
        self.recordtype_detector = self.wrap_operation(recordtype_detector, none_allowed=True)
        self.record_processor = self.wrap_operation(record_processor, none_allowed=True)

    def create_dataframe(self, data_file):
        records = []
        # Loop through lines in file
        record_number = 0
        while True:
            record_data = data_file.read(self.record_length)
            record_number += 1
            # Detect end of file
            if not record_data:
                break

            if self.recordtype_detector:
                record_type = self.run_wrapped_operation(self.recordtype_detector, record_data)
                # Skip record
                if record_type is None:
                    continue
            else:
                record_type = None

            # Build record dictionary
            record_dict = {self.RECORDTYPE_FIELD_NAME: record_type, self.RECORDNUMBER_FIELD_NAME: record_number}
            for field in self.fields:
                field.add_to_record(record_type, record_data, record_dict)

            # Apply record procsesing
            if self.record_processor:
                record_dict = self.run_wrapped_operation(self.record_processor, record_dict)
            # Add record to list
            records.append(record_dict)
        # Build DataFrame from records and headers
        return pd.DataFrame(records)

    def order_fields(self, dataframe):
        # Create ordered list of columns
        # Record type and number + defined fields
        expected_columns = ([self.RECORDTYPE_FIELD_NAME, self.RECORDNUMBER_FIELD_NAME] +
                            [field.name for field in self.fields if field.name in dataframe.columns])
        # Any other fields added (perhaps by record processor)
        extra_colums = [column for column in dataframe.columns if column not in expected_columns]
        dataframe = dataframe[expected_columns + extra_colums]
        return dataframe


class BFWField(InputField):
    """
    Base InputField class for Binary Fixed Width fields
    """
    def __init__(self, name, start_pos, length, blank_values=(b'\xff',), **kwargs):
        """

        :param str name: Field name
        :param int or dict start_pos: Byte start position (integer to apply to all record types,
        or dictionary mapping of record type to associated start_pos)
        :param int length: Byte length
        :param tuple/list blank_values: List/tuple of byte values for blank data.
        If entire field content consist of any of these bytes, return None value
        :param kwargs:
        """
        super().__init__(name, **kwargs)
        self.start_pos = start_pos
        self.length = length
        if not isinstance(blank_values, (list, tuple)):
            raise ValueError('blank_values should be sequence of bytes, not: "{}"'.format(blank_values))
        self.EMPTY_VALUES = set(blank_value * length for blank_value in blank_values)

    @profiled
    def add_to_record(self, recordtype, record_data, record_dict):
        """
        Get field value from record
        :param str recordtype: Record type name
        :param bytes record_data: Binary record data
        :param dict record_dict: Output record dictionary to add field value to
        :return:
        """
        if isinstance(self.start_pos, int):
            start_pos = self.start_pos
        elif recordtype in self.start_pos:
            start_pos = self.start_pos[recordtype]
        else:
            # Field not applicable to record type
            return

        raw_value = record_data[start_pos:start_pos + self.length]

        # Dont add empty / blank value to record (this logic is repeated in self.action() but saves function call)
        if raw_value in self.EMPTY_VALUES:
            return

        # Can call self.action() directly for better performance because this method is already profiled
        record_dict[self.name] = self.action(raw_value)


class HexField(BFWField):
    """
    Field class which converts values to hex representation
    """
    value_converter = BytesToHexString()


class StringField(BFWField):
    """
    Field class which decodes byte content to string
    """
    value_converter = BytesToString()


class IntegerField(BFWField):
    """
    Field which converts byte values to integer
    """
    def __init__(self, *args, bytes_reversed=False, **kwargs):
        """
        Add value converter to convert bytes to integer, and column converter to nullable integer to handle cases when
        there may be missing values in column
        :param args:
        :param bool bytes_reversed: Whether bytes are reversed (little endian byteorder encoding)
        :param kwargs:
        """
        super().__init__(*args, value_converter=BytesToInteger(byteorder='little' if bytes_reversed else 'big'),
                         column_converter=ToInteger(large=True), **kwargs)