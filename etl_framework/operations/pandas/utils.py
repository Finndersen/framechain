from functools import reduce
from operator import and_

import numpy as np
import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype, is_categorical_dtype, is_datetime64_any_dtype, \
    is_bool_dtype

from etl_framework.operations.pandas.exceptions import MaskMismatchError, ChangedDataTypeError, DTypeError, \
    LengthMismatchError


def optimise_dataframe(dataframe):
    """
    Check types and values of all columns in Dataframe to see if they can be optimised to save memory, e.g.:

    :param pd.DataFrame dataframe:
    :return:
    """
    optimisations = []
    dataframe = dataframe.copy()
    for column_name in dataframe.columns:
        dataframe[column_name], col_optimisations = optimise_series(dataframe[column_name])
        for optimisation in col_optimisations:
            optimisations.append('{}: {}'.format(column_name, optimisation))

    return dataframe, optimisations


def optimise_series(series):
    """
    Check types and values Series to see if it can be optimised to save memory, e.g.:
    - Convert and downcast numeric
    - Timestamp strings to datetime64
    - Convert to Categorical type
    Returns converted series and list of descriptions of optimisations made
    :param pd.Series series:
    :return:
    """
    optimisations = []

    # Don't optimise if already category
    if is_categorical_dtype(series):
        return series, optimisations

    mem_usage = series.memory_usage(deep=True)
    # Attempt to convert to numeric and downcast (if not datetime or  string starting with '0')
    if not (is_datetime64_any_dtype(series) or (is_string_dtype(series) and (series.str[0] == '0').any())):
        try:
            downcast_mem = mem_usage
            downcast_series = series
            downcast_type = None
            # Attempt each downcast option. If option isn't able to work (e.g. integer when values are float),
            # it won't downcast properly so need to try all of them and choose lowest option
            for downcast in 'unsigned', 'integer', 'float':
                s = pd.to_numeric(series, downcast=downcast)
                mem = s.memory_usage(deep=True)
                if mem < downcast_mem:
                    downcast_mem = mem
                    downcast_series = s
                    downcast_type = downcast

            if downcast_type:
                optimisations.append('Convert from {} to {} and downcast using: {} ({:.2f}% reduction)'.format(
                    series.dtype,
                    downcast_series.dtype,
                    downcast_type,
                    (1 - downcast_mem / mem_usage) * 100
                ))
                series = downcast_series
                mem_usage = downcast_mem

        except (ValueError, TypeError):
            # Unable to parse Series as numeric
            pass

    # Attempt convert timestamp strings to datetime
    if is_object_dtype(series):
        try:
            series = pd.to_datetime(series)

            optimisations.append('Convert to datetime64 ({:.2f}% reduction)'.format(
                (1 - series.memory_usage(deep=True) / mem_usage) * 100
            ))
            mem_usage = series.memory_usage(deep=True)
        except (ValueError, OverflowError):
            # Failed to parse as datetime
            pass

    # See if converting to categorical type saves memory
    category_series = series.astype('category')
    category_mem_saving = (1 - category_series.memory_usage(deep=True) / mem_usage) * 100
    # Suggest if greater than 20% saving
    if category_mem_saving > 20:
        optimisations.append('Convert from {} to Category type ({:.2f}% reduction)'.format(series.dtype,
                                                                                           category_mem_saving))
        series = category_series

    return series, optimisations


def union_indexes(indexes):
    """
    Union a collection of indexes
    :param indexes:
    :return:
    """
    merged_index = pd.Index([])
    for index in indexes:
        merged_index = merged_index.union(index)

    return merged_index


def concat_dataframes(dataframes, reset_index=True):
    """
    Concatenate a list of dataframes, aligning categorical column categories first to preserve dtype
    :param list dataframes: List of dataframes
    :param bool reset_index: Whether to reset index on merged dataframe
    :return:
    """
    # Shortcut for single DF
    if len(dataframes) == 1:
        merged = dataframes[0]
    else:
        # Align categories for common categorical columns
        common_columns = reduce(and_, (set(df.columns) for df in dataframes))
        for column_name in common_columns:
            first_df_column = dataframes[0][column_name]
            # Check for dtype mismatches
            if not all(is_same_dtype(df[column_name], first_df_column) for df in dataframes[1:]):
                # Align categories of categorical DTYPE
                if is_categorical_dtype(first_df_column):
                    all_categories = union_indexes(df[column_name].cat.categories for df in dataframes)
                    # Set new categories on column
                    for df in dataframes:
                        df[column_name] = df[column_name].cat.set_categories(all_categories)
                else:
                    raise DTypeError(
                        'DTypes of "{}" columns to concatenate are not equal: {}'.format(column_name,
                                                                                     [df[column_name].dtype
                                                                                      for df in dataframes]))

        merged = pd.concat(dataframes)

    if reset_index:
        merged = merged.reset_index(drop=True)

    return merged


def integrate_masked_series(dest_series, new_series, mask):
    """
    Integrate one series into another using a boolean mask
    Mask should have length equal to dest_series and length of new_series should be equal to number of
    True elements in mask

    :param pd.Series dest_series: Destination series to merge new content into
    :param pd.Series new_series: Series containing new data to integrate
    :param pd.Series, boolean array mask: Boolean array mask for merging new series data
    :return: pd.Series: New merged series
    """
    # Verify data is Series
    if not isinstance(new_series, pd.Series):
        raise TypeError('Expected Series data but got: {}'.format(type(new_series)))

    # Attempt to convert mask to Boolean series if not already
    if not isinstance(mask, pd.Series):
        mask = pd.Series(mask)

    # Mask must be boolean series
    if not is_bool_dtype(mask):
        raise TypeError('Mask must be a boolean Series, not {}'.format(mask.dtype))

    # Convert nullable-boolean type mask to standard boolean, because doesnt work when setting (nulls become falsey)
    if str(mask.dtype) == 'boolean':
        mask = mask.fillna(False).astype(bool)

    # Verify new_series length is equal to number of True elements in mask
    if len(new_series.index) != mask.sum():
        raise MaskMismatchError(
            'New Series length ({}) does not match boolean mask True value count ({})'.format(len(new_series.index),
                                                                                              mask.values.sum()))

    # Verify mask length is equal to destination series length
    if len(dest_series.index) != len(mask.index):
        raise LengthMismatchError(
            "Boolean Series mask must does not have same length ({}) as destination series ({})".format(len(mask.index),
                                                                                                        len(
                                                                                                            dest_series.index)))

    # Handle dtype mismatches
    if not is_same_dtype(dest_series, new_series):
        # If new series is completely null, can cast to destination dtype to re-integrate
        if new_series.isnull().all():
            new_series = new_series.astype(dest_series.dtype)
        else:
            # Raise error if datetime dtype of column has changed (can cause issues with timezone mismatch)
            if is_datetime64_any_dtype(dest_series):
                raise ChangedDataTypeError(
                    'Datetime datatype of masked values has changed from "{}" to "{}", which may have undesired effect. '
                    'Removing any conditions may resolve the issue'.format(dest_series.dtype, new_series.dtype))

            # If merging with existing Category column, need to align categories if different
            if is_categorical_dtype(dest_series):
                new_series = new_series.astype('category')
                all_categories = dest_series.cat.categories.union(new_series.cat.categories)
                dest_series = dest_series.cat.set_categories(all_categories)
                new_series = new_series.cat.set_categories(all_categories)

            # TODO: Other type checks/handling..

    # Make copy to avoid making changes to original Series
    result_series = dest_series.copy(deep=True)
    # Set index on new series data so it is aligned with existing (TODO: Dont need to do this for newer pandas)
    new_series.index = result_series.index[mask]
    # Merge into destination series using .iloc with mask to not overwrite existing values
    result_series.iloc[mask.values] = new_series

    # Verify Dtype of original series isn't changed
    if not is_same_dtype(result_series, dest_series) and not dest_series.isnull().all():
        raise ChangedDataTypeError(
            'Integrating "{}" series caused dtype to change from "{}" to "{}"'.format(new_series.dtype,
                                                                                      dest_series.dtype,
                                                                                      result_series.dtype))
    return result_series


def set_column_on_df(dataframe, column_name, column_data, align_index=True):
    """
    Used to set a column value on a DataFrame
    Column data must be series of same length as DataFrame, and will have index replaced with DF index so values are
    integrated as expected

    There is bug that causes data to be mutated in-place when setting new column of same dtype
    (https://github.com/pandas-dev/pandas/pull/43406)
    This causes update to also be reflected on any shallow copy parents, which is undesirable.
    TODO: Should be fixed in pandas v1.4.0

    :param pd.DataFrame dataframe:
    :param str column_name:
    :param pd.Series column_data:
    :param bool align_index: whether to reset index of column data before integrating
    :return:
    """

    if not isinstance(column_data, pd.Series):
        raise TypeError('Expected a Series, not "{}"'.format(type(column_data)))

    # Verify data is same length as destination DF
    if len(column_data.index) != len(dataframe.index):
        raise LengthMismatchError('Length of result Series ({}) is not the same as the destination DataFrame ({})'.format(
            len(column_data.index),
            len(dataframe.index)))

    # Clear existing column with same Dtype to avoid operating in-place
    # (could remove column entirely but then new one would be added at end of DF)
    if column_name in dataframe.columns and is_same_dtype(dataframe[column_name], column_data):
        dataframe[column_name] = np.nan

    # Set index so values are integrated as expected
    if align_index:
        column_data.index = dataframe.index

    dataframe[column_name] = column_data


def is_same_dtype(series1, series2):
    """
    Check if Dtype of two series is same
    There is a bug/issue when doing equality of a standard dtype with a pandas extension dtype which causes
    TypeError to be raised, however the equality works if done the other way around
    TODO: Fixed in  Numpy 1.21.1
    :param pd.Series series1:
    :param pd.Series series2:
    :return:
    """
    try:
        return series1.dtype == series2.dtype
    except TypeError:
        return series2.dtype == series1.dtype


def reset_index(df_or_series):
    """
    Reset the index of a DF or series by assigning a new one
    Is faster than df.reset_index() (makes a new copy) but changes index in-place
    :param df_or_series:
    :return:
    """
    df_or_series.index = pd.RangeIndex(len(df_or_series.index))
    return df_or_series