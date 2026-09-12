from unittest import TestCase
from datetime import timedelta, timezone, datetime
import pytz

from framechain.utils import convert_timezone, chunks


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
            [10 * 60, pytz.FixedOffset(10 * 60)],                                # Int
            [timedelta(minutes=10*60), pytz.FixedOffset(10 * 60)],          # timedelta
            [pytz.timezone('Australia/Victoria'), pytz.timezone('Australia/Victoria')],          # pytz.timezone
            [timezone(timedelta(minutes=10*60)), pytz.FixedOffset(10 * 60)], # other tzinfo object
            ['+11:00', pytz.FixedOffset(11 * 60)],
            ['-11:00', pytz.FixedOffset(-11 * 60)]
        ]
        dt = datetime(2020, 12, 1, 12, 30, 0)

        for input_val, expected_output in test_data:
            output = convert_timezone(input_val)
            self.assertTrue(hasattr(output, 'localize'))
            self.assertEqual(output.utcoffset(dt), expected_output.utcoffset(dt))
            self.assertEqual(output.tzname(dt), expected_output.tzname(dt))

    def test_chunks(self):
        """
        Test chunks function
        :return:
        """
        data = (1,2,3,4,5,6,7,8,9,10)

        # Test non-iterator with small chunk and leftover
        chunk_iter = chunks(data, 3)
        self.assertEqual(tuple(next(chunk_iter)), (1,2,3))
        self.assertEqual(tuple(next(chunk_iter)), (4, 5, 6))
        self.assertEqual(tuple(next(chunk_iter)), (7, 8, 9))
        self.assertEqual(tuple(next(chunk_iter)), (10, ))

        # Test iterator with large chunk and no leftover
        chunk_iter = chunks(iter(data), 5)
        self.assertEqual(tuple(next(chunk_iter)), (1,2,3, 4, 5))
        self.assertEqual(tuple(next(chunk_iter)), (6, 7, 8, 9, 10))

        # Test chunksize of None (should return all data)
        self.assertEqual(tuple(next(chunks(data, None))), data)

        # Test chunksize larger than data size (should return all data)
        self.assertEqual(tuple(next(chunks(data, 15))), data)


