import re, logging, io
import pandas as pd
from etl_framework.exceptions import ETLError, ETLConfigurationError
from etl_framework.operations.pandas.record_extractors.base import BaseDataFrameGenerator, InputField, IntegerFieldMixin, TimestampFieldMixin

log = logging.getLogger(__name__)


class RegexMatchError(ETLError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class RegexRecordExtractor(BaseDataFrameGenerator):
    """
    Extract records from text file by matching lines with Regex pattern with capture groups corresponding to fields
    Capture groups can be named or not
    """

    def __init__(self, fields, pattern, enforce_match=True, header_lines=0):
        """
        :param fields: Sequence of Field instances (Defining field names and conversion logic)
        :param str pattern: Regex pattern string with named groups corresponding to field contents
        :param bool enforce_match: Whether to raise error if record line does not match regex, otherwise skip record
        :param int header_lines: Number of header lines to skip
        """
        self.regex_pattern = re.compile(pattern)
        self.enforce_match = enforce_match
        self.header_lines = header_lines
        # Set capture group index on fields with group name specified
        for field in fields:
            if field.group_index is None:
                if field.group_name not in self.regex_pattern.groupindex:
                    self.error(ETLConfigurationError, 'Field {} does not have a named regex group in pattern: {}'.format(field,
                                                                                                                         pattern))
                field.group_index = self.regex_pattern.groupindex[field.group_name] - 1
        super().__init__(fields)

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
        return pd.DataFrame(data=self.get_records(file_reader))

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
                match_groups = match.groups()
                # Extract fields and perform value conversion
                yield {field.name: field(match_groups[field.group_index]) for field in self.fields}
            elif self.enforce_match:
                # Raise error for mismatching record line
                self.error(RegexMatchError, 'Line: "{}"" does not match pattern: "{}"'.format(recordline, self.regex_pattern.pattern))
            else:
                # Skip record
                pass
                # if log.level <= logging.DEBUG:
                #     log.debug('REGEX-MISMATCH',
                #               'Line: "{}"" does not match pattern: "{}"'.format(recordline, self.regex_pattern.pattern))


class RegexField(InputField):
    """
    Basic field to be used with RegexRecordExtractor
    """
    def __init__(self, name, group=None, **kwargs):
        """

        :param str name: Field name
        :param str/int group: Can either be regex capture group number (starting with 1) or name. Defaults to field name
        :param kwargs:
        """
        if isinstance(group, int):
            self.group_index = group - 1
            self.group_name = None
        else:

            self.group_name = group if isinstance(group, str) else name
            self.group_index = None
        super().__init__(name, **kwargs)


class IntegerField(IntegerFieldMixin, RegexField):
    """
    Field which converts values to integer
    """
    pass


class TimestampField(TimestampFieldMixin, RegexField):
    """
    Field for timestamps
    """
    pass


