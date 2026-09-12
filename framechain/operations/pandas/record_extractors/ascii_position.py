from framechain.operations.pandas.record_extractors.base import InputField
from framechain.operations.pandas.record_extractors.base import BaseDataFrameGenerator
import pandas as pd
import io, logging

log = logging.getLogger(__name__)


class ASCIIPartitionedRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from data file content with fields seperated by position
    Input data needs to be ASCII text with newline character line seperators
    TODO: NEEDS REWORKING
    """
    def __init__(self, fields, header_lines=0, record_skip_check=None):
        """
        :param fields: Tuple of PartitionedField
        :param header_lines: Number of header lines to skip
        :param record_skip_check: Optional function which takes raw string content of record line and returns boolean whether it should be skipped or not
        """
        self.record_skip_check = record_skip_check
        self.header_lines = header_lines
        super().__init__(fields)

    def create_dataframe(self, input_data):
        # Create readable file object from data
        file_reader = io.StringIO(input_data)
        # Skip header lines
        for i in range(self.header_lines):
            line = file_reader.readline().strip()
            log.debug('SKIP-HEADER', 'Skipping header line: "{}"'.format(line))

        # Build local tuple pairs of field positions for faster lookup than field attribute access
        field_positions = ((field.start_pos,field.end_pos) for field in self.fields)
        all_records = []
        # Loop through lines in file
        for line_num, recordline in enumerate(file_reader):
            # Skip line before extracting field values if necessary
            if self.record_skip_check and self.record_skip_check(recordline):
                continue

            # Build raw record
            raw_record = tuple((recordline[field_pos[0]:field_pos[1]] for field_pos in field_positions))

            all_records.append(raw_record)
        # Build dataframe with field names
        return pd.DataFrame(all_records, columns=(field.name for field in self.fields))


class PartitionedField(InputField):
    """
    Object to define details of partitioned field, such as start and end position in record line
    """
    def __init__(self, name, start_pos, end_pos, **kwargs):
        """

        :param str name: Field name
        :param int start_pos: Start position of field value in record line
        :param int end_pos: End position of field value in record line
        """
        self.start_pos = start_pos
        self.end_pos = end_pos
        super().__init__(name, **kwargs)