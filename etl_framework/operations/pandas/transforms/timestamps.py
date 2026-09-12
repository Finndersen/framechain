import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from etl_framework.operations.base import Operation
from etl_framework.operations.pandas.base import ColumnOperation
from etl_framework.operations.transforms.datetime import ConvertTimezone as ConvertTimezoneNormal, \
    SetTimezone as SetTimezoneNormal


#############################################################################################################
#   TIMESTAMP PARSING
#############################################################################################################


class ColumnToDatetime(ColumnOperation):
    """
    Convert a column of string values to datetime.
    Runs as vector operation so should be faster than all other scalar methods
    Will attempt to infer format if not provided

    If timestamps have different timezones (and utc=True not specified), output will be object array and
    ConvertColumnTimezone with different_timezones=True can be used to convert all to desired timezone
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
                                   **self.to_datetime_kwargs)
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

    def __init__(self, units='s', coerce_errors=False):
        """

        :param str units: Units of timedelta
        :param bool coerce_errors: Whether to coerce error values (invalid parsing) into NaT
        """
        super().__init__()
        if units not in self.VALID_UNITS:
            self.error(ValueError, 'Invalid timedelta units: "{}". Choose from: {}'.format(units, self.VALID_UNITS))
        self.units = units
        self.coerce_errors = coerce_errors

    def action(self, column):
        # Verify that column is numeric is unit is specified (earlier versions of pandas do not perform this check)
        # if self.units and not is_numeric_dtype(column):
        #     raise TypeError('Input must be numeric when units are specified')
        return pd.to_timedelta(column, unit=self.units,
                               errors='coerce' if self.coerce_errors else 'raise')

    def description(self):
        return "Value to timedelta with units: {}".format(self.units)


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
class SetColumnTimezone(SetTimezoneNormal):
    """
    Add timezone information to existing naive timestamp column, or remove timezone info from
    aware timestamp column
    """

    def action(self, timestamp_column):
        """
        :param timestamp_column: Timestamp type column or single value from one
        """
        return timestamp_column.dt.tz_localize(self.timezone)


class SetDynamicTimezone(Operation):
    """
    Transform used to add dynamic timezone information to pandas.Timestamp value
    Need to provide both timestamp and timezone value when calling
    """

    def action(self, timestamp, timezone):
        """
        :param timestamp: pandas.Timestamp value
        :param timezone: tzinfo instance
        """

        return timestamp.tz_localize(timezone)

    def description(self):
        return 'Set dynamic timezone'


class ConvertTimezone(ConvertTimezoneNormal):
    """
    Perform timezone conversion on datetime column or single Timestamp instance which is already timezone-aware
    Supports datetime columns with multiple timezones by first converting all to UTC
    """

    def action(self, timestamp_column):
        """

        :param timestamp_column: column (series) of pandas.Timestamp
        :return:
        """
        # Re-interpret timestamps with different timezones into UTC
        if not is_datetime64_any_dtype(timestamp_column):
            timestamp_column = pd.to_datetime(timestamp_column, utc=True)

        # Convert to desired timezone
        try:
            # Attempt conversion for Timestamp first
            return timestamp_column.tz_convert(self.timezone)
        except TypeError:
            # Attempt conversion for datetime Series
            return timestamp_column.dt.tz_convert(self.timezone)


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
