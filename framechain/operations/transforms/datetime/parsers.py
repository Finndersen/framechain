"""
Operations for parsing some kind of input (usually text) to datetime object
"""
import re
from datetime import time, date, datetime, timedelta, timezone
from framechain.exceptions import ConverterConfigurationError, ETLError, OperationConfigurationError
from framechain.operations import Operation


def StringToDatetime(format):
    """
    Helper function to return appropriate DateTime parser, choosing from (in order of speed):
    - Scalar preset-format parser
    - Scalar regex parser
    - Scalar .strptime() parser
    :param str format: Can be either:
    - datetime format string compatible with or datetime.strptime()
    - preset option from PresetDateTimeParser
    - Regex string containing named groups for year, month, day, hour, etc
    :param bool vectorised: Whether converter should operate on vector input (Series)
    :return:
    """
    if not isinstance(format, str):
        raise ValueError('Timestamp format must be string, not {}'.format(type(format).__name__))
    if format in PresetDateTimeParser.datetime_formats:
        return PresetDateTimeParser(format)
    else:
        try:
            return RegexDateTimeParser(format)
        except OperationConfigurationError:
            return BasicDatetimeParser(format)


class RegexDateTimeParser(Operation):
    """
    Parse a text timestamp into a python time object, using regex pattern
    Faster than strptime, slower than PresetDateTimeParser but much more flexible
    Output type depends on regex group names provided:
    year, month, day: Date
    hour, [minute, second, millisecond]: Time
    year, month, day, hour, [minute, second, millisecond]:  DateTime
    year, month, day, hour, [minute, second, millisecond], offset_hours, offset_minutes, offset_sign: Datetime with UTC offset
    month value can be number or 3-character abbreviation
    """
    # Mapping of Month Abbreviations to numbers
    month_abbrev_lookup = {
        'Jan': 1,
        'Feb': 2,
        'Mar': 3,
        'Apr': 4,
        'May': 5,
        'Jun': 6,
        'Jul': 7,
        'Aug': 8,
        'Sep': 9,
        'Oct': 10,
        'Nov': 11,
        'Dec': 12
    }

    def __init__(self, regex_pattern):
        """
        :param str regex_pattern: Regex string pattern for timestamp string
        """
        super().__init__()
        self.pattern = re.compile(regex_pattern) if isinstance(regex_pattern, str) else regex_pattern
        # Validate regex has required components
        group_names = self.pattern.groupindex
        self.has_date = all(x in group_names for x in ['year', 'month', 'day'])
        self.has_time = 'hour' in group_names
        self.has_utcoffset = all(x in group_names for x in ['offset_hours', 'offset_minutes', 'offset_sign'])
        if not (self.has_date or self.has_time):
            raise OperationConfigurationError('Regex pattern: {} does not contain Date or Time named groups'.format(regex_pattern))

    def action(self, timestamp_str):
        """

        :param str timestamp_str: String containing timestamp
        :return:
        """
        match= self.pattern.fullmatch(timestamp_str)
        if not match:
            raise ValueError('Timestamp string: "{}" does not match pattern: {}'.format(timestamp_str, self.pattern))

        match_dict = match.groupdict()
        # Create Datetime
        if self.has_date and self.has_time:
            # Get UTC Offset if present
            if self.has_utcoffset:
                offset_value = timedelta(hours=int(match_dict['offset_hours']), minutes=int(match_dict['offset_minutes']))
                if match_dict['offset_sign'] == '+':
                    pass
                elif match_dict['offset_sign'] == '-':
                    offset_value = -offset_value
                else:
                    raise ValueError('Invalid UTC offset sign: {}'.format(match_dict['offset_sign']))

                tzinfo = timezone(offset_value)
            else:
                tzinfo = None

            # Construct Datetime
            dt = datetime(int(match_dict['year']), self.get_month_value(match_dict['month']), int(match_dict['day']),
                          int(match_dict['hour']), int(match_dict.get('minute', 0)), int(match_dict.get('second', 0)),
                          int(match_dict.get('millisecond', 0)*1000),
                          tzinfo=tzinfo)
            return dt

        # Create Date
        elif self.has_date:
            return date(int(match_dict['year']), self.get_month_value(match_dict['month']), int(match_dict['day']))
        # Create Time
        else:
            return time(int(match_dict['hour']), int(match_dict.get('minute', 0)),
                        int(match_dict.get('second', 0)), int(match_dict.get('millisecond', 0))*1000)

    def get_month_value(self, match_val):
        """
        Get month value directly or translate from text abbreviation
        :param match_val:
        :return:
        """
        if match_val in self.month_abbrev_lookup:
            return self.month_abbrev_lookup[match_val]
        else:
            return int(match_val)


class PresetDateTimeParser(Operation):
    """
    Converts text string to datetime object
    Choose from selection of preset datetime formats (asterisk matches any character)
    For example, for HH:MM:SS, use datetime_format of HH*MM*SS
    Much Faster than datetime.strptime, slightly faster than regex method, but less flexible
    Can handle date, time or datetime formats
    """
    datetime_formats = {
        'HHMMSS': lambda s: time(int(s[0:2]), int(s[2:4]), int(s[4: 6])),
        'HH*MM*SS': lambda s: time(int(s[0:2]), int(s[3:5]), int(s[6: 8])),
        'YYYYMMDD': lambda s: date(int(s[0:4]), int(s[4:6]), int(s[6: 8])),
        'YYYY*MM*DD': lambda s: date(int(s[0:4]), int(s[5:7]), int(s[8: 10])),
        'YYYYMMDDHHMMSS': lambda s: datetime(int(s[0:4]), int(s[4:6]), int(s[6: 8]), int(s[8: 10]), int(s[10: 12]), int(s[12: 14])),
        'YYYY*MM*DD*HH*MM*SS': lambda s: datetime(int(s[0:4]), int(s[5:7]), int(s[8: 10]), int(s[11: 13]), int(s[14: 16]), int(s[17: 19])),
        'YYYY*MM*DD*HH*MM*SS*mmmmmm': lambda s: datetime(int(s[0:4]), int(s[5:7]), int(s[8: 10]), int(s[11: 13]), int(s[14: 16]), int(s[17: 19]), int(s[20: 26])),
        'DD*MM*YYYY*HH*MM*SS': lambda s: datetime(int(s[6:10]), int(s[3:5]), int(s[0: 2]), int(s[11: 13]), int(s[14: 16]), int(s[17: 19])),
    }

    def __init__(self, datetime_format):
        super().__init__()
        self.datetime_format = datetime_format
        try:
            self.parse_func = self.datetime_formats[datetime_format]
        except KeyError:
            raise ConverterConfigurationError('{} is not a configured datetime format for {}. Valid options are: {}'.format(datetime_format, type(self).__name__, self.datetime_formats.keys()))

    def action(self, raw_value):
        # Handle special case of Time value that needs 0-padding on hour
        if self.datetime_format == 'HH*MM*SS' and raw_value[1] == ':':
            raw_value = '0' + raw_value

        return self.parse_func(raw_value)


class BasicDatetimeParser(Operation):
    """
    Basic datetime parser using datetime.strptime()
    """
    def __init__(self, time_format):
        super().__init__()
        self.time_format = time_format

    def action(self, value):
        return datetime.strptime(value, self.time_format)


