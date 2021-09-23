from etl_framework.operations import Operation
from etl_framework.utils import convert_timezone


class SetTimezone(Operation):
    """
    Adds timezone information to naive datetime, or remove from aware datetime
    Timezone can be supplied as either:
    - Timezone name as string
    - UTC Offset in seconds as integer
    - UTC offset as timedelta
    - tzinfo instance (datetime.timezone, pytz.timezone, dateutil.tz.tz.tzoffset etc)
    - None (remove timezone information)
    """
    def __init__(self, timezone):
        """
        :param str, int, tzinfo, timedelta, None timezone: Timezone to add. If None, removes timezone information
        """
        super().__init__()
        self.timezone = convert_timezone(timezone, allow_none=True)

    def action(self, dt):
        """
        Set timezone of datetime object, or remove existing timezone
        :param datetime.datetime dt:
        :return:
        """
        if self.timezone is None:
            return dt.replace(tzinfo=None)
        else:
            return self.timezone.localize(dt)

    def description(self):
        if self.timezone is None:
            return 'Remove tzinfo from datetime'
        else:
            return 'Set timezone to: {}'.format(self.timezone)


class ConvertTimezone(Operation):
    """
    Performs timezone conversion for single timezone-aware datetime object
    Timezone can be supplied as either:
    - Timezone name as string
    - UTC Offset in seconds as integer
    - UTC offset as timedelta
    - tzinfo instance (datetime.timezone, pytz.timezone, dateutil.tz.tz.tzoffset etc)
    """
    def __init__(self, timezone):
        """
        :param str, int, tzinfo timezone: Timezone to convert to
        """
        super().__init__()
        self.timezone = convert_timezone(timezone, allow_none=False)

    def action(self, dt):
        """

        :param dt: datetime object
        :return:
        """
        if dt.tzinfo is None:
            self.error(ValueError, 'tzinfo attribute is set to None. Datetime object must be timezone-aware')

        return dt.astimezone(self.timezone)

    def description(self):
        return 'Convert timezone to {}'.format(self.timezone)