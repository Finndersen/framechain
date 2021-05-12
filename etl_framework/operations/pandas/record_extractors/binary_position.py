import pandas as pd
from etl_framework.operations.pandas.record_extractors.base import BaseDataFrameGenerator


class BinaryPositionSeperatedRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from binary data file with fields seperated by a  position
    """

    def __init__(self, file_reader, field_definitions, record_length, record_skip_check=None):
        """
        :param tuple field_definitions: Tuple of tuple-triplets containing field name, start pos, end pos
        :param int record_length: Length of full record line
        :param callable record_skip_check: Optional callable which takes raw string content of record line and returns boolean whether it should be skipped or not
        """
        self.field_positions = tuple((field_def[1], field_def[2]) for field_def in field_definitions)
        self.field_names = tuple(field_def[0] for field_def in field_definitions)
        self.record_length = record_length
        self.record_skip_check = record_skip_check

    def action(self, data_file):
        records = []
        # Loop through lines in file
        for recordline in self.read_binary_chunk(data_file):
            # Skip line before extracting field values if necessary
            if self.record_skip_check and self.record_skip_check(recordline):
                continue

            # Add record to list
            records.append([recordline[pos[0]:pos[1]] for pos in self.field_positions])
        # Build DataFrame from records and headers
        return pd.DataFrame(records, columns=self.field_names)

    def read_binary_chunk(self, data_file):
        """generator to read a file piece by piece"""
        while True:
            data = data_file.read(self.record_length)
            if not data:
                break
            yield data