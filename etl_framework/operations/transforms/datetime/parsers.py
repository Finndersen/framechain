"""
Operations for parsing some kind of input (usually text) to datetime object
"""
import re
from datetime import time, date, datetime, timedelta
from etl_framework.exceptions import ConverterConfigurationError, ETLError
from etl_framework.operations import ScalarOperation


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
    if format in PresetDateTimeParser.datetime_formats:
        return PresetDateTimeParser(format)
    elif all(group_name in format for group_name in RegexUTCOffsetDateTimeParser.required_components):
        return RegexUTCOffsetDateTimeParser(format)
    elif all(group_name in format for group_name in RegexNaiveDateTimeParser.required_components):
        return RegexNaiveDateTimeParser(format)
    elif all(group_name in format for group_name in RegexDateParser.required_components):
        return RegexDateParser(format)
    elif all(group_name in format for group_name in RegexTimeParser.required_components):
        return RegexTimeParser(format)
    else:
        return BasicDatetimeParser(format)


class RegexTimeParser(ScalarOperation):
    """
    Parse a text timestamp into a python time object, using regex pattern
    Faster than strptime, slower than PresetDateTimeParser but much more flexible
    Regex pattern must include named groups of hour, minute and second
    """
    required_components = ('hour', 'minute', 'second')

    def __init__(self, regex_pattern):
        """
        :param str regex_pattern: Regex string pattern for timestamp string
        """
        self.regex_pattern = re.compile(regex_pattern)
        # Validate regex has required components
        for component in self.required_components:
            if component not in self.regex_pattern.groupindex:
                raise ConverterConfigurationError('Missing regex named group: "{}" required for {}'.format(component, type(self).__name__))

    def __call__(self, raw_value):
        match_dict = self.regex_pattern.fullmatch(raw_value).groupdict()
        return time(int(match_dict['hour']), int(match_dict['minute']), int(match_dict['second']))


class RegexDateParser(RegexTimeParser):
    """
    Parse a date string into a python date object, using regex pattern
    Faster than strptime, slower than PresetDateTimeParser but much more flexible
    Regex pattern must include named groups of year, month or month_abbrev, and day
    """
    required_components = ('year', 'day')

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

    def get_month_value(self, match_dict):
        """
        Get month value directly or translate from text abbreviation
        :param match_dict:
        :return:
        """
        if 'month_abbrev' in match_dict:
            return self.month_abbrev_lookup[match_dict['month_abbrev']]
        else:
            return int(match_dict['month'])

    def __call__(self, raw_value):
        match_dict = self.regex_pattern.fullmatch(raw_value).groupdict()
        return date(int(match_dict['year']), self.get_month_value(match_dict), int(match_dict['day']))


class RegexNaiveDateTimeParser(RegexDateParser):
    """
    Parse a datetime string into a python naive datetime object, using regex pattern
    Faster than strptime, slower than PresetDateTimeParser but much more flexible
    Regex pattern must include named groups of: year, month or month_abbrev, day, hour, minute, second
    """

    required_components = RegexDateParser.required_components + ('hour', 'minute', 'second')

    def __call__(self, raw_value):
        match_dict = self.regex_pattern.fullmatch(raw_value).groupdict()
        return datetime(int(match_dict['year']), self.get_month_value(match_dict), int(match_dict['day']),
                        int(match_dict['hour']), int(match_dict['minute']), int(match_dict['second']))


class RegexUTCOffsetDateTimeParser(RegexNaiveDateTimeParser):
    """
    Parse a datetime string with UTC offset value into a python naive datetime object in UTC time, using regex pattern
    Faster than strptime, slower than PresetDateTimeParser but much more flexible
    Regex pattern must include named groups of: year, month or month_abbrev, day, hour, minute, second, offset_sign, offset_hours, offset_minutes
    """
    required_components = RegexNaiveDateTimeParser.required_components + ('offset_hours', 'offset_minutes', 'offset_sign')

    def __call__(self, raw_value):
        match_dict = self.regex_pattern.fullmatch(raw_value).groupdict()
        original_datetime =  datetime(int(match_dict['year']), self.get_month_value(match_dict), int(match_dict['day']),
                                      int(match_dict['hour']), int(match_dict['minute']), int(match_dict['second']))

        offset_value = timedelta(hours=int(match_dict['offset_hours']), minutes=int(match_dict['offset_minutes']))
        if match_dict['offset_sign'] == '+':
            return original_datetime - offset_value
        elif match_dict['offset_sign'] == '-':
            return original_datetime + offset_value
        else:
            raise ETLError('Invalid UTC offset sign: {}'.format(match_dict['offset_sign']))


class PresetDateTimeParser(ScalarOperation):
    """
    Converts text string to datetime object
    Choose from selection of preset datetime formats (asterisk matches any character)
    For example, for HH:MM:SS, use datetime_format of HH*MM*SS
    Much Faster than datetime.strptime, slightly faster than regex method, but less flexible
    Can handle date, time or datetime formats
    """
    datetime_formats = {
        'HHMMSS': (time, ((0, 2), (2, 4), (4, 6))),
        'HH*MM*SS': (time, ((0, 2), (3, 5), (6, 8))),
        'YYYYMMDD': (date, ((0, 4), (4, 6), (6, 8))),
        'YYYY*MM*DD': (date, ((0, 4), (5, 7), (8, 10))),
        'YYYYMMDDHHMMSS': (datetime, ((0, 4), (4, 6), (6, 8), (8, 10), (10, 12), (12, 14))),
        'YYYY*MM*DD*HH*MM*SS': (datetime, ((0, 4), (5, 7), (8, 10), (11, 13), (14, 16), (17, 19))),
        'YYYY*MM*DD*HH*MM*SS*mmmmmm': (datetime, ((0, 4), (5, 7), (8, 10), (11, 13), (14, 16), (17, 19), (20, 26))),
    }

    def __init__(self, datetime_format):
        self.datetime_format = datetime_format
        try:
            self.parse_config = self.datetime_formats[datetime_format]
        except KeyError:
            raise ConverterConfigurationError('{} is not a configured datetime format for {}. Valid options are: {}'.format(datetime_format, type(self).__name__, self.datetime_formats.keys()))

    def __call__(self, raw_value):
        # Handle special case of Time value that needs 0-padding on hour
        if self.datetime_format == 'HH:MM:SS' and raw_value[1] == ':':
            raw_value = '0' + raw_value

        return self.parse_config[0](*[int(raw_value[str_pos[0]:str_pos[1]]) for str_pos in self.parse_config[1]])


class BasicDatetimeParser(ScalarOperation):
    """
    Basic datetime parser using datetime.strptime()
    """
    def __init__(self, time_format):
        self.time_format = time_format

    def __call__(self, value):
        return datetime.strptime(value, self.time_format)


