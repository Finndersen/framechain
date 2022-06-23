"""
Operations which are used to help construct more complex field-based transforms with masking capability
"""
import inspect

import pandas as pd
from pandas.core.dtypes.common import is_list_like

from etl_framework.exceptions import InvalidOperationError, OperationConfigurationError, ETLError
from etl_framework.operations import Operation
from etl_framework.operations.pandas import Column, integrate_masked_series, set_column_on_df, \
    DropColumns, DropRows, RenameColumns, Explode, DataframeOperation
from etl_framework.utils import randomstring

pd.set_option('mode.chained_assignment', 'raise')  # Raise SetWithCopyError instead of warning


class SetColumn(DataframeOperation):
    """
    Assign a column/field values using a transformation operation. Creates new column if doesnt already exist in DataFrame
    Transformation operation takes DataFrame as input and returns a Series as output (with same length as input DF)
    The index on the resultant Series is reset/ignored
    """

    def __init__(self, column_name, transform):
        """
        :param str column_name: Name of column to populate output values in
        :param callable transform: Callable which takes Dataframe and returns Series.
        """
        super().__init__()
        self.operation = self.add_child_operation(transform)
        self.column_name = column_name

    def action(self, dataframe):
        """
        Perform transformation on dataframe
        :param pd.DataFrame dataframe:
        :return:
        """
        # Perform transformation on dataframe
        output_series = self.operation(dataframe)

        # Make copy so changes arent made to original DF
        new_dataframe = dataframe.copy(deep=False)

        # Manually assign new column data instead of using DataFrame.assign() which creates a deep copy and so not efficient
        set_column_on_df(new_dataframe, self.column_name, output_series)

        return new_dataframe

    def add_to_graph(self, graph):
        # Create Subgraph/cluster to contain wrapped operation
        from pydot import Cluster
        subgraph = Cluster(graph_name=randomstring(10),
                           label=self.short_description())
        start_node, end_node = self.operation.add_to_graph(subgraph)
        graph.add_subgraph(subgraph)
        return start_node, end_node

    def description(self):
        return 'Set column "{}" value using transform: {}'.format(self.column_name, self.operation)

    def short_description(self):
        return 'Set column "{}" value using transform'.format(self.column_name)

    def get_required_columns(self):
        return []


def ConvertColumn(column_name, column_transform):
    """
    Convenience function for defining a conversion transformation operation on a single column
    :param str column_name: name of field to convert
    :param column_transform:  Callable which performs transform operation on series and returns transformed series
    """
    return SetColumn(column_name, Column(column_name) >> column_transform)


class MapToColumns(DataframeOperation):
    """
    Apply a mapping function to a selection of dataframe columns to create a new Series
    The mapping function will be called for each row, and provided values of the specified columns
    as arguments. Should return a single value, which will be used as the row value for the
    output Series.

    :param func map_func: Mapping Function
    :param list/tuple/str columns: Dataframe column/s to use in a mapping function. If not
    specified, will use argument names of map_func
    """

    def __init__(self, map_func, columns=None, result_dtype=None):
        """

        :param map_func: Function to map to DataFrame column values
        :param list|None columns:
        :param result_dtype: dtype for result output Series (None to infer)
        """
        super().__init__()

        if not callable(map_func):
            raise ValueError("{} is not callable".format(map_func))

        func_args = inspect.getfullargspec(map_func).args
        if columns is None:
            # Use function argument names as columns
            columns = func_args
        elif isinstance(columns, str):
            columns = [columns]

        if not isinstance(columns, (list, tuple)):
            raise TypeError('Columns must be provided as list or  tuple')

        if len(columns) == 1:
            raise Exception('Should use Apply() operation for a single column')

        if len(columns) != len(func_args):
            raise ValueError('Number of specified columns ({}) is not equal to number of function arguments ({})'.format(len(columns),
                                                                                                                         len(func_args)))

        self.columns = columns
        self.map_func = map_func
        self.result_dtype = result_dtype

    def action(self, dataframe):
        """

        :param DataFrame dataframe:
        :return:
        """
        return pd.Series(data=map(self.map_func,
                                  *(dataframe[column_name] for column_name in self.columns)),
                         index=dataframe.index,
                         dtype=self.result_dtype)

    def description(self):
        return 'Maps the function {} to columns: {}'.format(self.map_func.__name__,
                                                            repr(self.columns))

    def get_required_columns(self):
        return self.columns


class UseColumns(DataframeOperation):
    """
    Select a subset of columns from a DataFrame to apply an operation to, and then re-integrate
    result back into original DF. Any new added columns are also included.
    Allows for better performance of operations applied to entire DF (e.g. Conditional, Apply,
    FillNA, AsType) when only subset of columns are required
    """

    def __init__(self, columns, transform, propagate_dropped_columns=True):
        """
        :param list columns: List of column names to select to create subset dataframe
        :param callable transform: Callable which takes sub-Dataframe and returns Dataframe of same length
        :param bool propagate_dropped_columns: Whether any columns removed from Sub-DF are also removed from original
        """
        super().__init__()
        if not isinstance(columns, (list, tuple)):
            raise TypeError('Columns must be provided as list or tuple')
        self.columns = columns
        self.transform = self.add_child_operation(transform)
        self.propagate_dropped_columns = propagate_dropped_columns

    def action(self, full_dataframe):
        """

        :param pd.DataFrame full_dataframe:
        :return:
        """
        # Make shallow copy so changes arent made to original DF
        full_dataframe = full_dataframe.copy(deep=False)
        # Call transform with subset of dataframe columns
        result_subset_df = self.transform(full_dataframe[self.columns].copy(deep=False))

        # Integrate result columns back into dataframe (including any extra columns added)
        for column_name in result_subset_df.columns:
            set_column_on_df(full_dataframe, column_name, result_subset_df[column_name])

        # Remove any deleted columns
        if self.propagate_dropped_columns:
            full_dataframe = full_dataframe.drop(columns=[column_name
                                                          for column_name in self.columns
                                                          if column_name
                                                          not in result_subset_df.columns])

        return full_dataframe

    def get_required_columns(self):
        return self.columns


class SetField(Operation):
    """
    Sets a value of a row field, and returns the row
    Similar to SetColumn but works on a row Series
    Should be used within an Apply() wrapper (better than using multiple instances of SetColumn with Apply(), since
    Apply() is expensive)
    """

    def __init__(self, field, transform):
        """
        :param str field: Name of column to populate output values in
        :param callable transform: Callable which either takes Series and returns a single value to set on the field
        """
        super().__init__()
        self.transform = self.add_child_operation(transform)
        self.field = field

    def action(self, row):
        row[self.field] = self.transform(row)
        return row

    def description(self):
        return 'Set field "{}" value using transform: {}'.format(self.field, self.transform)


class Apply(Operation):
    """
    Apply an operation to each element of input vector Series and return a resultant Series with
    transformed values. Can use in combination with Conditional() operation to apply to subset of
    input, e.g. skip null values
    """

    def __init__(self, operation, fast=True, convert_dtype=False, **kwargs):
        """
        :param operation: Operation to apply to each element of Series
        :param bool fast: If true and plain function is provided (not Operation instance), do not
        wrap function as Operation (avoids profiling for better performance)
        :param bool convert_dtype: Whether to try infer dtype for results. Default to False for
        better performance and avoid unexpected behaviour
        :param kwargs: Extra key-word arguments to provide to apply()
        """
        super().__init__()
        # Don't wrap and register provided function in fast mode (to avoid overheads)
        if fast and not isinstance(operation, Operation):
            self.operation = operation
        else:
            self.operation = self.add_child_operation(operation)

        if is_list_like(self.operation):
            raise TypeError('Do not provide list-like value to Apply: {}'.format(self.operation))

        self.convert_dtype = convert_dtype
        self.kwargs = kwargs

    def action(self, series):
        """
        :param pd.Series series:
        :return:
        """
        return series.apply(self.operation,
                            convert_dtype=self.convert_dtype,
                            **self.kwargs)

    def description(self):
        return 'Apply to each row: ({}) '.format(self.operation)


class SeriesWhere(Operation):
    """
    Used to conditionally apply an operation to an input series. Provided conditional operation is used to produce
    boolean mask, masked input series is passed to wrapped operation, and result integrated back into original input.
    """

    def __init__(self, condition, operation):
        """

        :param condition: Callable which takes Dataframe or Series and returns boolean series mask
        :param operation: Transform operation to apply to rows which meet condition
        """
        super().__init__()
        self.operation = self.add_child_operation(operation)
        self.condition = self.add_child_operation(condition)

    def action(self, df_or_series):
        """

        :param pd.DataFrame, pd.Series df_or_series:
        :return:
        """
        # Get mask using condition (should be read-only operation)
        mask = self.condition(df_or_series)

        # Validate mask
        if not pd.api.types.is_bool_dtype(mask):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))

        # Convert nullable-boolean type mask to standard boolean, because doesnt work when setting (nulls become falsey)
        if str(mask.dtype) == 'boolean':
            mask = mask.fillna(False).astype(bool)

        # Apply operation to masked DF content
        df_or_series = self.apply_operation_with_mask(df_or_series, self.operation, mask)

        return df_or_series

    def apply_operation_with_mask(self, series, operation, mask):
        """
        Apply operation to masked subset of input, and integrate result back in
        TODO: Maybe add shortcuts for All or None mask conditions? may just complicate things...
        :param pd.Series series:
        :param operation:
        :param pd.Series mask:
        :return: resultant DF or Series
        """
        if not isinstance(series, pd.Series):
            raise TypeError('Expected Series input, not: {}'.format(type(series)))

        # Provide masked data to operation (.iloc[mask.values] is a bit faster than .loc[mask])
        transformed_output = operation(series.iloc[mask.values])

        # Integrate values back into original Series
        series = integrate_masked_series(series,
                                         transformed_output,
                                         mask)
        return series

    def add_to_graph(self, graph):
        # Create Subgraph/cluster to contain wrapped operation
        from pydot import Cluster
        subgraph = Cluster(graph_name=randomstring(10),
                           label=self.short_description())
        start_node, end_node = self.operation.add_to_graph(subgraph)
        graph.add_subgraph(subgraph)
        # TODO: Need to add graph visualisation for inverse operation...
        return start_node, end_node

    def description(self):
        desc = 'Mask input with condition ({}) and apply ({})'.format(self.condition, self.operation)
        return desc

    def short_description(self):
        return 'Apply operation with mask condition ({})'.format(self.condition)


class DFWhere(SeriesWhere, DataframeOperation):
    """
    Used to conditionally apply an operation to an input DataFrame. Provided conditional operation is used to produce
    boolean mask, masked input DataFrame is passed to wrapped operation, and result integrated back into original input.
    Transform operation can add new columns and/or transform existing.

    By default, attempts to infer which columns are required by and affected/created by provided transforms by checking
    for instances of Column() and SetColumn() operations. This can result in significantly improved performance by
    avoiding unnecessary copying and replacing of data. However, if columns are changed or added in some other way then
    they may be ignored and will need to manually specify list of required_columns and affected_columns
    (or set to ALL_COLUMNS)
    """

    def __init__(self, condition, operation, affected_columns=None, required_columns=None):
        """

        :param condition: Callable which takes Dataframe or Series and returns boolean series mask
        :param operation: Transform operation to apply to rows which meet condition
        :param list, None affected_columns: List of columns affected/created by transform
        By default, will attempt to infer column names by checking for instances of SetColumn operation.
        :param list, None required_columns: List of columns required as input to conditional transforms
        By default, will attempt to infer column names by checking for
        """
        super().__init__(condition, operation)

        invalid_operations = (DropRows, DropColumns, RenameColumns, Explode)
        if self.search(lambda op: isinstance(op, invalid_operations)):
            raise InvalidOperationError(
                'Do not use following operations within DFWhere: {}'.format([op_class.__name__
                                                                             for op_class in invalid_operations]))

        self.required_columns = self._validate_columns(required_columns
                                                       if required_columns is not None
                                                       else self._get_inferred_required_columns())
        if self.required_columns == self.ALL_COLUMNS:
            print('Using all columns: {}'.format(self))
        self.affected_columns = self._validate_columns(affected_columns
                                                       if affected_columns is not None
                                                       else self._get_inferred_affected_columns())

    def _get_inferred_required_columns(self):
        """
        Infer columns required by transformation operation
        :return:
        """
        # Get full list of columns required by sub-operations
        required_columns = set()
        for operation in self.operation.search(lambda op: isinstance(op, DataframeOperation)):
            cols = operation.get_required_columns()
            if cols == self.ALL_COLUMNS:
                return cols
            elif cols:
                required_columns.update(cols)

        if not required_columns:
            raise OperationConfigurationError(
                'Unable to automatically detect columns required by operation: {}.\nPlease specify required_columns (or set to ALL_COLUMNS or NO_COLUMNS)'.format(self.operation))

        return required_columns

    def _get_inferred_affected_columns(self):
        """
        Infer columns changed/affected by transformation operation
        :return:
        """
        # Infer from SetColumn() operations
        affected_columns = set(setcolumn_op.column_name for setcolumn_op
                               in self.operation.search(lambda op: isinstance(op, SetColumn)))
        if not affected_columns:
            raise OperationConfigurationError(
                'Unable to automatically detect columns affected by operation: {}.\nPlease specify affected_columns or set to ALL'.format(self.operation))

        return affected_columns

    def _validate_columns(self, provided_columns):
        """
        Validate columns provided for required_columns or affected_columns
        :param list, set, tuple provided_columns: Column list provided
        :param list, set, tuple inferred_columns: Automatically inferred columns
        :return:
        """
        if provided_columns in [self.ALL_COLUMNS, self.NO_COLUMNS]:
            return provided_columns
        else:
            # Validate affected columns format
            if not isinstance(provided_columns, (set, tuple, list)):
                raise TypeError('columns should be a sequence, not: "{}"'.format(type(provided_columns)))

            if not all(isinstance(col_name, str) for col_name in provided_columns):
                raise TypeError('columns should be a sequence of strings, not: "{}"'.format(provided_columns))

            return list(provided_columns)

    def apply_operation_with_mask(self, dataframe, operation, mask):
        """
        Apply operation to masked subset of input, and integrate result back in
        TODO: Maybe add shortcuts for All or None mask conditions? may just complicate things...
        :param pd.DataFrame dataframe:
        :param operation:
        :param pd.Series mask:
        :return: resultant DF or Series
        """
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError('Expected DataFrame , not: {}'.format(type(dataframe)))

        # Get filtered input for transformation operation
        # df.iloc[mask.values] is a bit faster than df.loc[mask]
        # df.iloc[boolean_mask] routes to df.take() and returns a copy
        if self.required_columns == self.ALL_COLUMNS:
            # Use all columns
            transform_input = dataframe.iloc[mask.values]
        elif self.required_columns == self.NO_COLUMNS:
            # Transform input is empty masked dataframe
            transform_input = dataframe[[]].iloc[mask.values]
        else:
            # Use only columns required by transformation operation
            # selecting required fields first then doing iloc is faster and more memory efficient than
            # doing combined df.loc(mask, columns)
            transform_input = dataframe[self.required_columns].iloc[mask.values]

        transformed_output = operation(transform_input)

        # Verify output is also DataFrame
        if not isinstance(transformed_output, pd.DataFrame):
            raise TypeError(
                'Expected DataFrame output from DataFrame input, but got: {}'.format(type(transformed_output)))

        # Make copy to avoid making changes to original DF
        result_df = dataframe.copy(deep=False)
        # Integrate values back into original Dataframe
        for column_name in transformed_output.columns:
            # Only update column data if new or in affected column list
            if ((self.affected_columns == self.ALL_COLUMNS) or
                    (column_name not in result_df.columns) or
                    (column_name in self.affected_columns)):
                try:
                    # Integrate with existing column (or null series if new column) using mask
                    set_column_on_df(
                        result_df,
                        column_name,
                        integrate_masked_series(
                            result_df[column_name] if column_name in result_df.columns else
                            # Create empty null Series to integrate with if column does not already exist
                            pd.Series(index=result_df.index,
                                      dtype=transformed_output[column_name].dtype),
                            transformed_output[column_name],
                            mask))
                except Exception as exc:
                    raise ETLError('Error while assigning column: "{}" on DataFrame.\n{}: {}'.format(
                        column_name,
                        type(exc).__name__,
                        str(exc))) from exc

        return result_df

    def get_required_columns(self):
        # This operation does not require columns directly (its suboeprations do)
        return []


class ConstructDataFrame(Operation):
    """
    Construct a DataFrame from input data
    """

    def __init__(self, **init_kwargs):
        """

        :param init_kwargs: Keyword arguments for DataFrame initialisation
        """
        super().__init__()
        self.init_kwargs = init_kwargs

    def action(self, data):
        return pd.DataFrame(data=data,
                            **self.init_kwargs)


class ConstructSeries(Operation):
    """
    Construct a Series from input data
    """

    def __init__(self, **init_kwargs):
        """

        :param init_kwargs: Keyword arguments for Series initialisation
        """
        super().__init__()
        self.init_kwargs = init_kwargs

    def action(self, data):
        return pd.Series(data=data,
                         **self.init_kwargs)
