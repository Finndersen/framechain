import re, logging, io
import pandas as pd
from etl_framework.exceptions import ETLError
from etl_framework.operations.pandas.record_extractors.base import BaseRecordExtractor

log = logging.getLogger(__name__)


class RegexMatchError(ETLError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class RegexStringRecordExtractor(BaseRecordExtractor):
    """
    Extract records from text file by matching lines with Regex pattern with named groups corresponding to fields
    """

    def __init__(self, regex_pattern, enforce_match=True, header_lines=0):
        """
        :param str regex_pattern: Regex pattern string with named groups corresponding to field contents
        :param bool enforce_match: Whether to raise error if record line does not match regex, otherwise skip record
        :param int header_lines: Number of header lines to skip
        """
        self.regex_pattern = re.compile(regex_pattern)
        self.enforce_match = enforce_match
        self.header_lines = header_lines
        super().__init__([])

    def create_dataframe(self, file_reader):
        """

        :param file_reader: File reader object in text mode (has read, readlines methods and iterates over rows)
        :return:
        """
        # Skip header lines
        for i in range(self.header_lines):
            line = file_reader.readline()
            log.debug('Skipping header line: "{}"'.format(line))

        # Convert list of dictionary records into DataFrame
        return pd.DataFrame(self.get_records(file_reader))

    def get_records(self, file_reader):
        """
        Yield records as dictionaries of key-value pairs
        :param file_reader:
        :return:
        """
        # Loop through remaining lines in file
        for recordline in file_reader:
            match = self.regex_pattern.match(recordline)
            if match:
                yield match.groupdict()
            elif self.enforce_match:
                # Raise error for mismatching record line
                raise RegexMatchError('Line: "{}"" does not match pattern: "{}"'.format(recordline, self.regex_pattern.pattern))
            else:
                # Skip record
                log.debug('REGEX-MISMATCH',
                          'Line: "{}"" does not match pattern: "{}"'.format(recordline, self.regex_pattern.pattern))