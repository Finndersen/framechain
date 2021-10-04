import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype, is_categorical_dtype, is_datetime64_any_dtype, union_categoricals
from operator import and_
from functools import reduce


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



