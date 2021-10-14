from unittest import TestCase

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

from etl_framework.operations.pandas import concat_dataframes, integrate_masked_series, MaskMismatchError, \
    ChangedDataTypeError, set_column_on_shallow_copy_df, DTypeError


class UtilsTests(TestCase):
    """
    Test cases for Pandas util functions
    """

    def test_concat_dataframes(self):
        """
        Test concat_dataframes() utility function
        :return:
        """
        # Verify categorical type columns are aligned and index is reset
        s1 = pd.Series(['a', 'b', 'a'], dtype='category')
        self.assertEqual(list(s1.cat.categories),
                         ['a', 'b'])
        df1 = pd.DataFrame({'a': s1})

        s2 = pd.Series(['c', 'd'], dtype='category')
        self.assertEqual(list(s2.cat.categories),
                         ['c', 'd'])
        df2 = pd.DataFrame({'a': s2})

        merged_df = concat_dataframes([df1, df2])

        assert_frame_equal(merged_df,
                           pd.DataFrame({'a': pd.Series(['a', 'b', 'a', 'c', 'd'], dtype='category')}))
        self.assertEqual(list(merged_df['a'].cat.categories),
                         ['a', 'b', 'c', 'd'])

        # Verify error raised when concat different dtypes
        with self.assertRaises(DTypeError):
            concat_dataframes([pd.DataFrame({'a': [1, 2, 3]}),
                               pd.DataFrame({'a': ['a', 'b', 'c']})])

        # Test case of single DF (values should be same, but not same object (due to index reset)
        assert_frame_equal(concat_dataframes([df1]), df1)
        self.assertIsNot(concat_dataframes([df1]), df1)

    def test_integrate_masked_series(self):
        """
        Test integrate_masked_series() utility function
        :return:
        """

        # Verify TypeError raised if mask is invalid
        with self.assertRaises(TypeError):
            integrate_masked_series(pd.Series(),
                                    pd.Series(),
                                    ['invalid', None])

        original_series = pd.Series([1, 2, 3, 4, 5])
        original_copy = original_series.copy(deep=True)
        new_data = pd.Series([10, 10])
        mask_list = [False, True, False, True, False]
        result_series = pd.Series([1, 10, 3, 10, 5])

        # Verify error if count of mask True elements do not match new data length
        with self.assertRaises(MaskMismatchError):
            integrate_masked_series(original_series, new_data, [False, True, False, False, False])

        # Verify error if mask length is not equal to destination series length
        with self.assertRaises(MaskMismatchError):
            integrate_masked_series(original_series, new_data, [False, True, False, True])

        # Verify expected behaviour with different mask types
        for mask in [
            mask_list,  # Boolean list mask
            np.array(mask_list, dtype=bool),  # Numpy boolean array
            pd.Series(mask_list, dtype=bool),  # Boolean series
            pd.Series(mask_list, dtype='boolean'),  # Nullable Boolean series

        ]:
            assert_series_equal(
                integrate_masked_series(original_series, new_data, mask),
                result_series)

        # Verify original series not mutated
        assert_series_equal(original_series, original_copy)

        # Verify full mask
        assert_series_equal(
            integrate_masked_series(original_series, result_series, pd.Series([True, True, True, True, True])),
            result_series
        )

        # Verify empty mask
        assert_series_equal(
            integrate_masked_series(original_series, pd.Series(), pd.Series([False, False, False, False, False])),
            original_series
        )

        # Verify error is raised if dtype of original series is changed
        with self.assertRaises(ChangedDataTypeError):
            integrate_masked_series(original_series,
                                    pd.Series(['string', 'data']),
                                    mask_list)
        # But not if new data is nulls
        assert_series_equal(
            integrate_masked_series(original_series.astype('Int8'),
                                    pd.Series([None, None]),
                                    mask_list),
            pd.Series([1, None, 3, None, 5], dtype='Int8'))

        # Verify merging of categorical series
        assert_series_equal(
            integrate_masked_series(pd.Series(['a', 'b', 'c', 'a', 'b'], dtype='category'),
                                    pd.Series(['c', 'd'], dtype='category'),
                                    [True, True, False, False, False]),
            pd.Series(['c', 'd', 'c', 'a', 'b'], dtype='category')
        )

    def test_set_column_on_shallow_copy_df(self):
        """
        Test set_column_on_shallow_copy_df() utility function
        :return:
        """
        original_data = pd.Series([1, 2, 3, 4, 5])
        new_data = pd.Series(['a', 'b', 'c', 'd', 'e'])
        original_df = pd.DataFrame({'a': original_data})
        original_copy = original_df.copy(deep=True)

        shallow_copy = original_df.copy(deep=False)

        # Verify setting new data on shallow copy does not make change on original
        set_column_on_shallow_copy_df(shallow_copy, 'a', new_data)

        assert_frame_equal(shallow_copy, pd.DataFrame({'a': new_data}))
        assert_frame_equal(original_df, original_copy)
