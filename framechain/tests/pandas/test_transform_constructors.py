from unittest import TestCase
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

from framechain.operations import Value, OperationError
from framechain.operations.pandas import SetColumn, Column, LengthMismatchError
from framechain.tests.base import ETLFrameworkTestCase


class TestTransformConstructors(ETLFrameworkTestCase):

    def test_set_column(self):
        """
        Tests for SetColumn operation
        :return:
        """
        original_df = pd.DataFrame({
            'a': [1,2,3],
            'b': ['a', 'b', 'c']
        })
        original_copy = original_df.copy(deep=True)

        # Test replacing existing column (ignoring index of new data)
        result_df = SetColumn('a', pd.Series([4, 5, 6], index=[2, 1, 0]))(original_df)
        assert_frame_equal(result_df, pd.DataFrame({
            'a': [4, 5, 6],
            'b': ['a', 'b', 'c']
        }))
        # Verify original not mutated
        assert_frame_equal(original_df, original_copy)

        # Test adding new column
        result_df = SetColumn('c', pd.Series([4, 5, 6], index=[2, 1, 0]))(original_df)
        assert_frame_equal(result_df, pd.DataFrame({
            'a': [1,2,3],
            'b': ['a', 'b', 'c'],
            'c': [4, 5, 6],
        }))

        # Verify error if new data is not Series
        with self.assertRaisesOperationError(TypeError):
            SetColumn('c', 'Not a series')(original_df)

        # Verify error if new data is not same length as DF
        with self.assertRaisesOperationError(LengthMismatchError):
            SetColumn('a', pd.Series([4, 5, 6, 7]))(original_df)




