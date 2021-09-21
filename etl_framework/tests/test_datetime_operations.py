from datetime import datetime
from unittest import TestCase
from pytz import timezone, utc
from dateutil.tz.tz import tzoffset

from etl_framework.operations import SetTimezone, OperationError, ConvertTimezone


class DatetimeOperationsTests(TestCase):
    naive_datetime = datetime(2021, 1, 1, 0, 0, 0)
    timezone_aware_date = datetime(2021, 1, 1, 0, 0, 0, tzinfo=utc)
    offset_aware_date = datetime(2021, 1, 1, 0, 0, 0, tzinfo=tzoffset('UTC+10:00:00', 60 * 60 * 10))

    def test_SetTimezone(self):
        """
        Tests transform logic of AddTimezone function
        """

        data = [
            (self.naive_datetime, SetTimezone('Australia/Brisbane'), datetime(2021, 1, 1, tzinfo=tzoffset('UTC+10:00:00', 60 * 60 * 10))),
            (self.naive_datetime, SetTimezone(60 * 60 * 10), timezone('Australia/Brisbane').localize(datetime(2021, 1, 1))),
            (self.naive_datetime, SetTimezone(), datetime(2021, 1, 1, tzinfo=tzoffset('UTC+00:00:00', 0))),
            (self.timezone_aware_date, SetTimezone(None), datetime(2021, 1, 1, 0, 0, 0))  # Remove timezone
            ]

        for input_date, transform, output_date in data:
            self.assertEqual(transform(input_date), output_date)

        # Verify error raised when trying to set timezone on non-naive datetime
        with self.assertRaises(OperationError):
            SetTimezone()(self.timezone_aware_date)

    def test_ConvertTimezone(self):
        """
        Tests transform logic of ToTimezone function
        """
        data = [
            (self.timezone_aware_date, ConvertTimezone('Australia/Brisbane'),
             timezone('Australia/Brisbane').localize(datetime(2021, 1, 1, 10, 0, 0))),
            (self.offset_aware_date, ConvertTimezone('Australia/Perth'),
             datetime(2020, 12, 31, 22, tzinfo=tzoffset('UTC+08:00:00', 60*60*8))),
            (self.offset_aware_date, ConvertTimezone(), datetime(2020, 12, 31, 14, tzinfo=utc)),
        ]

        for input_date, transform, output_date in data:
            self.assertEqual(transform(input_date), output_date)

        # Verify error raised when trying to convert timezone on naive datetime
        with self.assertRaises(OperationError):
            ConvertTimezone()(self.naive_datetime)

        # Verify error raised when initialising with timezone as None
        with self.assertRaises(TypeError):
            ConvertTimezone(None)
