import pandas as pd
import pytz
from pandas.api.types import is_datetime64_any_dtype

from etl_framework.operations.base import Operation
from etl_framework.operations.pandas.base import ColumnOperation
#############################################################################################################
#   TIMESTAMP PARSING
#############################################################################################################
from etl_framework.utils import convert_timezone


class ColumnToDatetime(ColumnOperation):
    """
    Convert a column of string values to datetime
    Runs as vector operation so should be faster than all other scalar methods
    Will attempt to infer format if not provided
    If timestamps have different timezones, output will be object array and ConvertColumnTimezone
    with different_timezones=True can be used to convert all to desired timezone
    """
    changes_type = True

    def __init__(self, format=None, **to_datetime_kwargs):
        """
        :param str format: Datetime string format as strptime() format code
        :param to_datetime_kwargs: extra kwargs to provide to pd.to_datetime()
        """
        super().__init__()
        self.format = format
        self.to_datetime_kwargs = to_datetime_kwargs

    def action(self, column):
        # Get Timestamp series from strings
        dt_series = pd.to_datetime(column,
                                   format=self.format,
                                   infer_datetime_format=not self.format,
                                   **self.to_datetime_kwargs)
        # to_datetime() will not convert to datetime64 type if timestamp format string contains timezone information
        # (%z) and no valid values are matched. So attempt conversion again just to get appropriate type
        if not is_datetime64_any_dtype(dt_series):
            dt_series = pd.to_datetime(dt_series)
        return dt_series

    def description(self):
        return '{} with format: {}'.format(type(self).__name__, self.format)


class ToTimedelta(ColumnOperation):
    """
    Convert a column to Timedelta values
    Supports string values or numbers:
    to_timedelta('1 days 06:05:01.00003')
    pd.to_timedelta('15.5us')
    pd.to_timedelta(np.arange(5), unit='s')
    """
    VALID_UNITS = {'D', 'h', 'm', 's', 'ms', 'us', 'ns'}

    def __init__(self, units='s'):
        """

        :param str units: Units of timedelta
        """
        super().__init__()
        if units not in self.VALID_UNITS:
            self.error(ValueError, 'Invalid timedelta units: "{}". Choose from: {}'.format(units, self.VALID_UNITS))
        self.units = units

    def action(self, column):
        return pd.to_timedelta(column, unit=self.units)

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
        super().__init__()
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
        super().__init__()
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
        super().__init__()
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
        super().__init__()
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
        super().__init__()
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
        super().__init__()
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
    Format Timestamp series to String, and replace missng values with specified string

    In pandas versions before 1.0, dt.strftime() returned 'NaT' string for NaT values,
    whereas later versions (e.g. 1.2) return np.NaN values.

    """

    def __init__(self, format='%Y-%m-%d %H:%M:%S', null_value=''):
        """

        :param str format: Datetime format string
        :param str null_value: Value to substitute empty values for (None to skip substitution)
        """
        super().__init__()
        self.format = format
        self.null_value = null_value

    def action(self, series):

        formatted_series = series.dt.strftime(self.format)
        # If entire series is NaT, output series will be NaN float-type series
        # If series is mixture of NaT and value times, output will be object series with strings and NaN values
        if self.null_value is not None:
            if int(pd.__version__[0]) < 1:
                formatted_series = formatted_series.str.replace('NaT', self.null_value)
            else:
                formatted_series = formatted_series.fillna(self.null_value)

        return formatted_series

    def description(self):
        return 'DatetimeToString format: "{}"'.format(self.format)


class TimedeltaToSeconds(ColumnOperation):
    """
    Convert a Timedelta column to a total number of seconds float column
    """

    def action(self, timedelta_column):
        return timedelta_column.dt.total_seconds()
