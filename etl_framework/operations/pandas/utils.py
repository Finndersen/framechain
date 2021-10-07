import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype, is_categorical_dtype, is_datetime64_any_dtype, is_bool_dtype
from operator import and_
from functools import reduce

from etl_framework.exceptions import ChangedDataTypError


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
                    (1-downcast_mem/mem_usage)*100
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
                (1-series.memory_usage(deep=True)/mem_usage)*100
            ))
            mem_usage = series.memory_usage(deep=True)
        except (ValueError, OverflowError):
            # Failed to parse as datetime
            pass

    # See if converting to categorical type saves memory
    category_series = series.astype('category')
    category_mem_saving = (1-category_series.memory_usage(deep=True)/mem_usage)*100
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


def concat_dataframes(dataframes):
    """
    Concatenate a list of dataframes, aligning categorical column categories first to preserve dtype
    :param dataframes:
    :return:
    """
    # Shortcut for single DF
    if len(dataframes) == 1:
        return dataframes[0]

    # Align categories for common categorical columns
    common_columns = reduce(and_, (set(df.columns) for df in dataframes))
    for column_name in common_columns:
        if is_categorical_dtype(dataframes[0][column_name]):
            all_categories = union_indexes(df[column_name].cat.categories for df in dataframes)
            # Set new categories on column
            for df in dataframes:
                df[column_name] = df[column_name].cat.set_categories(all_categories)

    return pd.concat(dataframes)


def integrate_masked_series(dest_series, new_series, mask):
    """
    Integrate one series into another using a boolean mask
    If mask is provided, should have length equal to dest_series and length of new_series should be equal to number of
    True elements in mask

    :param pd.Series dest_series: Destination series to merge new content into
    :param pd.Series new_series: Series containing new data to integrate
    :param pd.Series mask: Boolean array mask for merging new series data
    :return: pd.Series: New merged series
    """
    # Mask must be boolean series
    if not (isinstance(mask, pd.Series) and is_bool_dtype(mask)):
        raise TypeError('Mask must be a boolean Series, not {}'.format(mask.dtype if isinstance(mask, pd.Series)
                                                                       else type(mask)))

    # Convert nullable-boolean type mask to standard boolean, because doesnt work when setting (nulls become falsey)
    if str(mask.dtype) == 'boolean':
        mask = mask.fillna(False).astype(bool)

    # If merging with existing Category column, need to align categories
    if is_categorical_dtype(dest_series):
        new_series = new_series.astype('category')
        all_categories = dest_series.cat.categories.union(new_series.cat.categories)
        dest_series = dest_series.cat.set_categories(all_categories)
        new_series = new_series.cat.set_categories(all_categories)

    if dest_series.dtype != new_series.dtype:
        # Raise error if datetime dtype of column has changed (can cause issues with timezone mismatch)
        if is_datetime64_any_dtype(dest_series):
            raise ChangedDataTypError(
                'Datetime datatype of masked values has changed from "{}" to "{}", which may have undesired effect. '
                'Removing any conditions may resolve the issue'.format(dest_series.dtype, new_series.dtype))
        # TODO: Other type checks..

    # Verify new_series length is equal to number of True elements in mask
    if len(new_series.index) != mask.sum():
        raise ValueError('New Series length ({}) does not match boolean mask True value count ({})'.format(len(new_series.index),
                                                                                                           mask.values.sum()))
    # Make copy to avoid making changes to original Series
    result_series = dest_series.copy()
    # Need to use .iloc with mask to not overwrite existing values
    result_series.iloc[mask.values] = new_series

    return result_series
