from etl_framework.record_extractors.files.delimited import log
from etl_framework.record_extractors.base import InputField
from etl_framework.record_extractors.files.base import FileRecordExtractor
import pandas as pd


class ASCIIPartitionedRecordExtractor(FileRecordExtractor):
    """
    Extract records from data file with fields seperated by position
    Data file assumed to be ASCII text with newline character line seperators
    """
    def __init__(self, file_reader, fields, header_lines=0, record_skip_check=None):
        """
        :param fields: Tuple of ParitionedField
        :param header_lines: Number of header lines to skip
        :param record_skip_check: Optional function which takes raw string content of record line and returns boolean whether it should be skipped or not
        """
        self.record_skip_check = record_skip_check
        self.header_lines = header_lines
        super().__init__(file_reader, fields)

    def dataframe_from_file(self, data_file):
        # Skip header lines
        for i in range(self.header_lines):
            line = data_file.readline().strip()
            log.debug('SKIP-HEADER', 'Skipping header line: "{}"'.format(line))

        # Build local tuple pairs of field positions for faster lookup than field attribute access
        field_positions = ((field.start_pos,field.end_pos) for field in self.fields)
        all_records = []
        # Loop through lines in file
        for line_num, recordline in enumerate(data_file):
            # Skip line before extracting field values if necessary
            if self.record_skip_check and self.record_skip_check(recordline):
                continue

            # Build raw record
            raw_record = tuple((recordline[field_pos[0]:field_pos[1]] for field_pos in field_positions))

            all_records.append(raw_record)
        # Build dataframe with field names
        return pd.DataFrame(all_records, columns=(field.name for field in self.fields))


class ParitionedField(InputField):
    """
    Object to define details of partitioned field, such as start and end position in record line
    """
    def __init__(self, name, start_pos, end_pos, column_converter=None):
        """

        :param str name: Field name
        :param int start_pos: Start position of field value in record line
        :param int end_pos: End position of field value in record line
        """
        self.start_pos = start_pos
        self.end_pos = end_pos
        super().__init__(name, column_converter)