import re
from datetime import time, date, datetime, timedelta
from etl_framework.operations.base import ScalarOperation, ScalarOrVectorOperation, DataframeOperation, ColumnOperation
from etl_framework.exceptions import ETLConfigurationError, ConverterConfigurationError, ETLError
import pytz
import pandas as pd


#############################################################################################################
#   TIMESTAMP PARSING
#############################################################################################################
def StringToDatetime(format=None, vectorised=True):
    """
    Helper function to generate appropriate DateTime parser, choosing from (in order of speed):
    - Vectorised pd.to_datetime() implementation
    - Scalar preset-format parser
    - Scalar regex parser
    - Scalar .strptime() parser
    :param str format: Can be either:
    - datetime format string compatible with pd.to_datetime() or datetime.strptime()
    - preset option from PresetDateTimeParser
    - Regex string containing named groups for year, month, day, hour, etc
    :param bool vectorised: Whether converter should operate on vector input (Series)
    :return:
    """
    if vectorised:
        return StringColumnToDatetime(format)
    else:
        if not format:
            raise ETLConfigurationError('Timestamp format must be provided when not using vectorised parsing method')
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


class StringColumnToDatetime(ColumnOperation):
    """
    Converter to convert column of string values to datetime
    Runs as vector operation so should be faster than all other methods
    Format does not need to be supplied if string is ISO format
    ISO format timestamp strings will have much better performance
    """
    changes_type = True

    def __init__(self, format=None):
        """
        :param str format: Datetime string format as strptime() format code
        """
        self.format = format

    def __call__(self, column):
        # Get Timestamp series from strings
        dt_series = pd.to_datetime(column, format=self.format, infer_datetime_format=True)

        return dt_series


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


class ToTimedelta(ColumnOperation):
    """
    Convert a column of integers to Timedelta values
    """
    VALID_UNITS = {'D','h','m','s','ms','us','ns'}

    #{'Y', 'M', 'W', 'D', 'days', 'day', 'hours', 'hour', 'hr', 'h', 'm', 'minute',  'minutes', 'seconds', 'second', 'ms', 'milliseconds','microseconds',  'ns', 'nanoseconds', 'nano', 'nanos', 'nanosecond'}
    def __init__(self, units='s'):
        """

        :param str units: Units of timedelta
        """
        if units not in self.VALID_UNITS:
            raise ConverterConfigurationError('Invalid timedelta units: "{}"'.format(units))
        self.units=units

    def __call__(self, int_column):
        return pd.to_timedelta(int_column, unit=self.units)

    def __str__(self):
        return "Integer to timedelta with units: {}".format(self.units)


class TimestampFromColumns(DataframeOperation):
    """
    Construct Timestamp series using date and time components in Dataframe columns
    Looks for columns names:
    Required: year, month, day
    Optional:  hour, minute, second, millisecond, microsecond, nanosecond
    """
    def __init__(self, timestamp_components=None):
        if timestamp_components is None:
            timestamp_components = ['year', 'month', 'day', 'hour', 'minute', 'second']
        self.timestamp_components = timestamp_components

    def __call__(self, dataframe):
        return pd.to_datetime(dataframe[self.timestamp_components])


#############################################################################################################
#   TIMEZONES
#############################################################################################################
class SetTimezone(ScalarOrVectorOperation):
    """
    Transform used to add timezone information to existing timestamp field
    Can operate on vector or scalar values
    Can initialise with single timezone to apply to all values, or can use ArgumentMapper to provide different timezone
    for each value (only when input_type = value)
    """

    def __init__(self, timezone=None, input_type='column'):
        """

        :param str, pytz.timezone, dateutil.tz.tzfile, None timezone: Timezone to apply to all values.
        Use None to remove timezone information but not change timestamp
        """
        self.timezone = timezone
        super().__init__(input_type)

    def __call__(self, timestamp, timezone=None):
        """
        :param timestamp: Timestamp type column or single value from one
        """
        if self.input_type == 'column':
            return timestamp.dt.tz_localize(self.timezone)
        else:
            timezone = timezone or self.timezone
            if not timezone:
                raise ValueError('Must provide timezone during initialisation or during execution with ArgumentMapper')
            return timestamp.tz_localize(timezone)

    def __str__(self):
        if self.input_type == 'column' or self.timezone:
            return 'Set timezone to: {}'.format(self.timezone)
        else:
            return 'Set varying timezone'


class ConvertTimezone(ScalarOrVectorOperation):
    """
    Perform timezone conversion on either entire column or individual Timestamp values which are already timezone-aware
    Set different_timezones=True when timestamps in column may have different timezones
    """

    def __init__(self, input_type='column', timezone=pytz.utc, different_timezones=False):
        """
        :param str input_type: Expected input type (column or value)
        :param str, pytz.timezone, dateutil.tz.tzfile timezone: Timezone to convert to (default to UTC).
        If None, will convert to UTC and remove timezone information
        :param bool different_timezones: Whether or not column contains timestamps in varying timezones
        """
        self.timezone = pytz.timezone(timezone) if isinstance(timezone, str) else timezone
        self.different_timezones = different_timezones
        super().__init__(input_type)

    def __call__(self, timestamp):
        """

        :param timestamp: Can be either column (series) of pandas.Timestamp, or single datetime.datetime value
        :return:
        """

        if self.input_type == 'column':
            if self.different_timezones:
                # Re-interpret timestamps with different timezones into UTC
                timestamp = pd.to_datetime(timestamp, utc=True)
                # Convert to other timezone if necessary
                if self.timezone != pytz.utc:
                    return timestamp.dt.tz_convert(self.timezone)
                else:
                    return timestamp
            else:
                # All timestamps have same timezone, can use tz_convert directly
                return timestamp.dt.tz_convert(self.timezone)
        else:
            # Convert scalar value
            return timestamp.tz_convert(self.timezone)

    def __str__(self):
        return 'Convert timezone to {}'.format(self.timezone)


class DateTimeProperty(ScalarOrVectorOperation):
    """
    Used to access Datetime or Timedelta properties of Series or Timestamp value
    See https://pandas.pydata.org/pandas-docs/stable/reference/series.html#api-series-dt for list of properties
    """
    def __init__(self, property_name, **kwargs):
        super().__init__(**kwargs)
        self.property_name = property_name

    def __call__(self, value):
        """

        :param value: Datetime or Timedelta Series, or Timestamp value
        :return:
        """
        if self.input_type == 'column':
            return getattr(value.dt, self.property_name)
        else:
            return getattr(value, self.property_name)


# class DateAndTimeToDatetime(object):
#     """
#     Create pandas datetime by joining Date and Time fields
#     Uses StringToDatetime converter, so can also specify original_timezone and output_timezone
#
#     This transform could actually be completely replaced using operators and wrappers etc
#     """
#     def __init__(self, date_format='%Y-%m-%d', time_format='%H:%M:%S', **converter_kwargs):
#         """
#         :param str date_format: format of date
#         :param str time_format: format of time
#         :param converter_kwargs: extra kwargs to pass too StringToDatetime initialisation (e.g. original and output timezone)
#         """
#         self.datetime_converter = StringToDatetime(format=date_format + ' ' + time_format, **converter_kwargs)
#
#     def __call__(self, date_column, time_column):
#         return self.datetime_converter(date_column.astype(str) + ' ' + time_column.astype(str))
#
#
#
