from etl_framework.operations.base import BaseOperation
from etl_framework.operations.pandas.base import DataframeOperation, ColumnOperation
from etl_framework.exceptions import ConverterConfigurationError
import pytz
import pandas as pd


#############################################################################################################
#   TIMESTAMP PARSING
#############################################################################################################

class StringColumnToDatetime(ColumnOperation):
    """
    Converter to convert column of string values to datetime
    Runs as vector operation so should be faster than all other scalar methods
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
class SetColumnTimezone(ColumnOperation):
    """
    Transform used to add timezone information to existing timestamp column
    """

    def __init__(self, timezone):
        """

        :param str, pytz.timezone, dateutil.tz.tzfile, None timezone: Timezone to apply to all values.
        Use None to remove timezone information but not change timestamp
        """
        self.timezone = timezone

    def __call__(self, timestamp_column):
        """
        :param timestamp_column: Timestamp type column or single value from one
        """
        return timestamp_column.dt.tz_localize(self.timezone)

    def __str__(self):
        return 'Set timezone to: {}'.format(self.timezone)


class SetTimezone(BaseOperation):
    """
    Transform used to add timezone information to pandas.Timestamp value
    Can initialise with single timezone to apply to all values, or can use ArgumentMapper to provide different timezone
    for each value
    """

    def __init__(self, timezone=None):
        """

        :param str, pytz.timezone, dateutil.tz.tzfile, False timezone: Timezone to apply to all values.
        Use False to remove timezone information but not change timestamp
        """
        self.timezone = timezone

    def __call__(self, timestamp, timezone=None):
        """
        :param timestamp: pandas.Timestamp value
        """
        timezone = timezone or self.timezone

        if timezone is None:
            self.error(ValueError, 'Must provide timezone during initialisation or during execution with ArgumentMapper')
        elif timezone is False:
            timezone = None

        return timestamp.tz_localize(timezone)

    def __str__(self):
        if self.timezone:
            return 'Set timezone to: {}'.format(self.timezone)
        else:
            return 'Set varying timezone'


class ConvertColumnTimezone(ColumnOperation):
    """
    Perform timezone conversion on either entire Timestamp column which is already timezone-aware
    Set different_timezones=True if timestamps in column may have different timezones
    """

    def __init__(self, timezone=pytz.utc, different_timezones=False):
        """
        :param str, pytz.timezone, dateutil.tz.tzfile timezone: Timezone to convert to (default to UTC).
            If None, will convert to UTC and remove timezone information
        :param bool different_timezones: Whether or not column contains timestamps in varying timezones
        """
        self.timezone = pytz.timezone(timezone) if isinstance(timezone, str) else timezone
        self.different_timezones = different_timezones

    def __call__(self, timestamp_column):
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

    def __str__(self):
        return 'Convert timezone to {}'.format(self.timezone)


class ConvertTimezone(BaseOperation):
    """
    Perform timezone conversion for single Timestamp value which is already timezone-aware
    """

    def __init__(self, timezone=pytz.utc):
        """
        :param str, pytz.timezone, dateutil.tz.tzfile timezone: Timezone to convert to (default to UTC).
        If None, will convert to UTC and remove timezone information
        """
        self.timezone = pytz.timezone(timezone) if isinstance(timezone, str) else timezone

    def __call__(self, timestamp):
        """

        :param timestamp: pandas.Timestamp value
        :return:
        """
        # Convert scalar value
        return timestamp.tz_convert(self.timezone)

    def __str__(self):
        return 'Convert timezone to {}'.format(self.timezone)


class DateTimeProperty(BaseOperation):
    """
    Used to access Datetime or Timedelta properties of Timestamp Series
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
        return getattr(value.dt, self.property_name)


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
