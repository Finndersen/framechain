import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype, is_categorical_dtype, is_datetime64_any_dtype


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

        except ValueError:
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



