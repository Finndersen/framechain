from unittest import TestCase
from datetime import timedelta, timezone, datetime
import pytz

from etl_framework.utils import StaticOffsetTz, convert_timezone


class UtilsTests(TestCase):
    """
    Test case for utility functions
    """

    def test_convert_timezone(self):
        """
        Test convert_timezone utility function
        :return:
        """

        with self.assertRaises(TypeError):
            convert_timezone(None)

        self.assertEqual(convert_timezone(None, allow_none=True), None)

        test_data = [
            ['Australia/Victoria', pytz.timezone('Australia/Victoria')],                            # TZ str
            ['UTC', pytz.utc],                                                                      # UTC Str
            [10*60*60, StaticOffsetTz(timedelta(seconds=10*60*60))],                                # Int
            [timedelta(seconds=10*60*60), StaticOffsetTz(timedelta(seconds=10*60*60))],          # timedelta
            [pytz.timezone('Australia/Victoria'), pytz.timezone('Australia/Victoria')],          # pytz.timezone
            [timezone(timedelta(seconds=10*60*60)), StaticOffsetTz(timedelta(seconds=10*60*60))] # other tzinfo object
        ]
        dt = datetime(2020, 12, 1, 12, 30, 0)

        for input_val, expected_output in test_data:
            output = convert_timezone(input_val)
            self.assertTrue(hasattr(output, 'localize'))
            self.assertEqual(output.utcoffset(dt), expected_output.utcoffset(dt))
            self.assertEqual(output.tzname(dt), expected_output.tzname(dt))