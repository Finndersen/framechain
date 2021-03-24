import pandas as pd
import pytz

from etl_framework.operations.base import Operation
from etl_framework.operations.pandas.base import ColumnOperation
#############################################################################################################
#   TIMESTAMP PARSING
#############################################################################################################
from etl_framework.utils import convert_timezone


class StringColumnToDatetime(ColumnOperation):
    """
    Convert a column of string values to datetime
    Runs as vector operation so should be faster than all other scalar methods
    Format does not need to be supplied if string is ISO format
    If timestamps have different timezones, output will be object array and ConvertColumnTimezone
    with different_timezones=True can be used to convert all to desired timezone
    """
    changes_type = True

    def __init__(self, format=None):
        """
        :param str format: Datetime string format as strptime() format code
        """
        self.format = format

    def action(self, column):
        # Get Timestamp series from strings
        dt_series = pd.to_datetime(column, format=self.format, infer_datetime_format=True)

        return dt_series


class ToTimedelta(ColumnOperation):
    """
    Convert a column of integers to Timedelta values
    """
    VALID_UNITS = {'D', 'h', 'm', 's', 'ms', 'us', 'ns'}

    # {'Y', 'M', 'W', 'D', 'days', 'day', 'hours', 'hour', 'hr', 'h', 'm', 'minute',  'minutes', 'seconds', 'second', 'ms', 'milliseconds','microseconds',  'ns', 'nanoseconds', 'nano', 'nanos', 'nanosecond'}
    def __init__(self, units='s'):
        """

        :param str units: Units of timedelta
        """
        if units not in self.VALID_UNITS:
            self.error(ValueError, 'Invalid timedelta units: "{}". Choose from: {}'.format(units, self.VALID_UNITS))
        self.units = units

    def action(self, int_column):
        return pd.to_timedelta(int_column, unit=self.units)

    def description(self):
        return "Integer to timedelta with units: {}".format(self.units)


class TimestampFromColumns(Operation):
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

    def action(self, dataframe):
        return pd.to_datetime(dataframe[self.timestamp_components])


#############################################################################################################
#   TIMEZONES
#############################################################################################################
class SetColumnTimezone(ColumnOperation):
    """
    Add timezone information to existing naive timestamp column, or remove timezone info from aware timestamp column
    """

    def __init__(self, timezone):
        """

        :param str, int, tzinfo, None timezone: Timezone to apply to all values.
        Use None to remove timezone information but not change timestamp
        """
        self.timezone = convert_timezone(timezone, allow_none=True)

    def action(self, timestamp_column):
        """
        :param timestamp_column: Timestamp type column or single value from one
        """
        return timestamp_column.dt.tz_localize(self.timezone)

    def description(self):
        if self.timezone:
            return 'Set timezone to: {}'.format(self.timezone)
        else:
            return 'Remove timezone'


class SetTimezone(Operation):
    """
    Transform used to add timezone information to pandas.Timestamp value
    Can initialise with single timezone to apply to all values, or can use ArgumentMapper to provide different timezone
    for each value
    """

    def __init__(self, timezone=None):
        """

        :param str, int, tzinfo, False timezone: Timezone to apply to all values.
        Use False to remove timezone information but not change timestamp
        """
        self.timezone = convert_timezone(timezone, allow_none=True)

    def action(self, timestamp, timezone=None):
        """
        :param timestamp: pandas.Timestamp value
        """
        timezone = timezone or self.timezone

        if timezone is None:
            self.error(ValueError,
                       'Must provide timezone during initialisation or during execution with ArgumentMapper')
        elif timezone is False:
            timezone = None

        return timestamp.tz_localize(timezone)

    def description(self):
        if self.timezone:
            return 'Set timezone to: {}'.format(self.timezone)
        else:
            return 'Set varying timezone'


class ConvertColumnTimezone(ColumnOperation):
    """
    Perform timezone conversion on either entire Timestamp column which is already timezone-aware
    Set different_timezones=True if timestamps in column may have different timezones
    """

    def __init__(self, timezone='UTC', different_timezones=False):
        """
        :param str, int, tzinfo, None timezone: Timezone to convert to (default to UTC).
            If None, will convert to UTC and remove timezone information
        :param bool different_timezones: Whether or not column contains timestamps in varying timezones
        """
        self.timezone = convert_timezone(timezone, allow_none=True)
        self.different_timezones = different_timezones

    def action(self, timestamp_column):
        """

        :param timestamp_column: column (series) of pandas.Timestamp
        :return:
        """
        if self.different_timezones:
            # Re-interpret timestamps with different timezones into UTC
            timestamp_column = pd.to_datetime(timestamp_column, utc=True)
            # Convert to other timezone if necessary
            if self.timezone != pytz.utc:
                return timestamp_column.dt.tz_convert(self.timezone)
            else:
                return timestamp_column
        else:
            # All timestamps have same timezone, can use tz_convert directly
            return timestamp_column.dt.tz_convert(self.timezone)

    def description(self):
        if self.timezone is None:
            return 'Convert timezone to UTC and remove tzinfo'
        else:
            return 'Convert timezone to {}'.format(self.timezone)


class ConvertTimezone(Operation):
    """
    Perform timezone conversion for single Timestamp value which is already timezone-aware
    """

    def __init__(self, timezone=pytz.utc):
        """
        :param str, int, tzinfo, None timezone: Timezone to convert to (default to UTC).
        If None, will convert to UTC and remove timezone information
        """
        self.timezone = convert_timezone(timezone, allow_none=True)

    def action(self, timestamp):
        """

        :param timestamp: pandas.Timestamp value
        :return:
        """
        # Convert scalar value
        return timestamp.tz_convert(self.timezone)

    def description(self):
        if self.timezone is None:
            return 'Convert timezone to UTC and remove tzinfo'
        else:
            return 'Convert timezone to {}'.format(self.timezone)


class DateTimeProperty(ColumnOperation):
    """
    Used to access Datetime or Timedelta properties of Timestamp Series
    See https://pandas.pydata.org/pandas-docs/stable/reference/series.html#api-series-dt for list of properties
    """

    def __init__(self, property_name):
        self.property_name = property_name

    def action(self, value):
        """

        :param value: Datetime or Timedelta Series
        :return:
        """
        return getattr(value.dt, self.property_name)

    def description(self):
        return 'Get DateTime property: "{}"'.format(self.property_name)


class DatetimeToString(ColumnOperation):
    """
    Format Timestamp series to String
    """

    def __init__(self, format='%Y-%m-%d %H:%M:%S'):
        """

        :param str format: Datetime format string
        """
        self.format = format

    def action(self, series):
        return series.dt.strftime(self.format)

    def description(self):
        return 'DatetimeToString format: "{}"'.format(self.format)

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
