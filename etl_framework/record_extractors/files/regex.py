import re

import pandas as pd

from etl_framework import exceptions
from etl_framework.record_extractors.files.delimited import log
from etl_framework.record_extractors.base import BaseRecordExtractor


class ASCIIRegexGroupsRecordExtractor(BaseRecordExtractor):
    """
    Match record lines to a regex pattern and split record into dictionary using regex named groups
    Data file assumed to be ASCII text with newline character line seperators
    """

    def __init__(self, regex_pattern, enforce_match=True, header_lines=0):
        """
        :param regex_pattern: Regex pattern string with named groups corresponding to field contents
        :param enforce_match: Whether to raise error if record line does not match regex, otherwise skip record
        :param header_lines: Number of header lines to skip
        :param strip_whitespaces: Whether to strip whitespaces from field content
        """
        self.regex_pattern = re.compile(regex_pattern)
        self.enforce_match = enforce_match
        self.header_lines = header_lines

    def __call__(self, data_file):
        # Skip header lines
        for i in range(self.header_lines):
            line = data_file.readline().strip()
            log.debug('SKIP-HEADER', 'Skipping header line: "{}"'.format(line))

        # Initialise record list
        records = []
        # Loop through remaining lines in file
        for line_num, recordline in enumerate(data_file):
            match = self.regex_pattern.match(recordline)
            if match:
                records.append(match.groupdict())
            elif self.enforce_match:
                # Raise error for mismatching record line
                raise exceptions.RecordMatchError(
                    'Line: "{}"" does not match pattern: "{}"'.format(recordline, self.regex_pattern.pattern))
            else:
                # Skip record
                log.debug('REGEX-MISMATCH',
                          'Line: "{}"" does not match pattern: "{}"'.format(recordline, self.regex_pattern.pattern))
        # Convert list of dictionary records into DataFrame
        return pd.DataFrame(records)