"""
Operations which are used to help construct more complex field-based transforms with masking capability
"""
import pandas as pd
from pandas.core.dtypes.common import is_list_like

pd.set_option('mode.chained_assignment', 'raise')  # Raise SetWithCopyError instead of warning
from etl_framework.operations import Operation
from etl_framework.operations.pandas import Field, integrate_masked_series, set_column_on_df
from etl_framework.utils import randomstring


class SetColumn(Operation):
    """
    Set a column/field values using a transformation operation. Creates new column if doesnt already exist in DataFrame
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
        return 'Set column "{}" value'.format(self.column_name)


def ConvertColumn(column_name, column_transform):
    """
    Convenience function for defining a conversion transformation operation on a single column
    :param str column_name: name of field to convert
    :param column_transform:  Callable which performs transform operation on series and returns transformed series
    """
    return SetColumn(column_name, Field(column_name) >> column_transform)


class UseColumns(Operation):
    """
    Select a subset of columns from a DataFrame to apply an operation to, and then re-integrate result back into
    original DF
    Allows for better performance of operations applied to entire DF (e.g. Apply, FillNA) when only subset of fields
    are required
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
        result_subset_df = self.run_child_operation(self.transform,
                                                    full_dataframe[self.columns].copy(deep=False))

        # Integrate result columns back into dataframe (including any extra columns added)
        for column_name in result_subset_df.columns:
            set_column_on_df(full_dataframe, column_name, result_subset_df[column_name])

        # Remove any deleted columns
        if self.propagate_dropped_columns:
            full_dataframe = full_dataframe.drop(columns=[column_name for column_name in self.columns
                                                          if column_name not in result_subset_df.columns])

        return full_dataframe


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
    Apply an operation to each element of input vector (DataFrame or Series) and return a resultant vector
    with transformed values.
    Can use in combination with Conditional() operation to apply to subset of vector input, e.g. skip null values

    When doing Apply() on Dataframe (iterating through Rows):
    - If transform returns a Series for each row, end result will be a DataFrame
    - Otherwise, end result will be Series of values returned from transform
    - Can use ApplyToColumns to select only the columns required by the transform for better performance
    - Do not add new fields to Series within the transform (performance is very bad).
    Best to pre-populate with null column beforehand
    - Series indexing in general has poor performance, best to convert from Series to Array or list
    (Series.values or Series.values.tolist()), use that within transform, then return list/array, resulting in a Series
    of lists/arrays which can be used to construct a new Dataframe with same columns as input. E.g.:
    Apply(transform_operation) >> ToList() >> ConstructDataFrame(columns=COLUMNS_OF_OUTPUT)
    """

    def __init__(self, operation, error_if_field_added=True, fast=False):
        """
        :param operation: Operation to apply to each element of vector
        :param bool error_if_field_added: Whether to raise error if result is DataFrame with additional field added.
        (Due to poor performance, should initialise blank placeholder column first) Can disable if result DF is
        constructed from arrays instead of adding extra fields to Series.
        :param bool fast: Whether to skip wrapping provided function as an operation for less overheads and better
        performance (does nothing if Operation instance provided)
        """
        super().__init__()
        # Don't wrap and register provided function in fast mode (to avoid overheads)
        if fast and not isinstance(operation, Operation):
            self.operation = operation
        else:
            self.operation = self.add_child_operation(operation)

        if is_list_like(self.operation):
            raise TypeError('Do not provide list-like value to Apply: {}'.format(self.operation))

        self.error_if_field_added = error_if_field_added

    def action(self, df_or_series):
        """
        :param df_or_series: Dataframe or Column (series)
        :return:
        """
        # Apply to DataFrame
        if isinstance(df_or_series, pd.DataFrame):
            result = df_or_series.apply(self.operation, axis=1)
            # Raise error if output is DF with new columns added (poor performance)
            if self.error_if_field_added and isinstance(result, pd.DataFrame) and any(column not in df_or_series.columns
                                                                                      for column in result.columns):
                raise Exception('Applied transform ({}) adds a new field, which has very poor performance. '
                                'Best to initialise the field as a blank column beforehand'.format(self.operation))

            return result
        # Apply to Series
        elif isinstance(df_or_series, pd.Series):
            return df_or_series.apply(self.operation)
        else:
            self.error(TypeError, 'Input should be DataFrame or Series')

    def description(self):
        return 'Apply to each row: ({}) '.format(self.operation)


class Conditional(Operation):
    """
    Conditional wrapper which takes Dataframe or Series input, applies conditional logic to produce boolean mask,
    passes masked content to wrapped operation, and then integrates result back into original input.
    If input is DataFrame, operation can add new columns and/or transform existing
    Can also provide an inverse operation to apply to the inverted condition content (like If-Else functionality)
    TODO: Rename to something better
    """

    def __init__(self, condition, operation, inverse_operation=None):
        """

        :param condition: Callable which takes Dataframe or column and returns boolean series mask
        :param operation: Operation to pass masked column to
        :param inverse_operation: Optional operation to apply to data from inverted mask
        """
        super().__init__()
        self.operation = self.add_child_operation(operation)
        self.condition = self.add_child_operation(condition)
        self.inverse_operation = self.add_child_operation(inverse_operation, none_allowed=True)

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

        # Apply inverse operation if provided
        if self.inverse_operation:
            df_or_series = self.apply_operation_with_mask(df_or_series, self.inverse_operation, ~mask)

        return df_or_series

    def apply_operation_with_mask(self, df_or_series, operation, mask):
        """
        Apply operation to masked subset of input, and integrate result back in
        TODO: Maybe add shortcuts for All or None mask conditions? may just complicate things...
        :param df_or_series:
        :param operation:
        :param pd.Series mask:
        :return: resultant DF or Series
        """
        # Provide masked data to operation (.iloc[mask.values] is a bit faster than .loc[mask])
        transformed_output = self.run_child_operation(operation,
                                                      df_or_series.iloc[mask.values])

        if isinstance(df_or_series, pd.DataFrame):
            # Verify output is also DataFrame
            if not isinstance(transformed_output, pd.DataFrame):
                raise TypeError(
                    'Expected DataFrame output from DataFrame input, but got: {}'.format(type(transformed_output)))

            # Make copy to avoid making changes to original DF
            result_df = df_or_series.copy(deep=False)
            # Integrate values back into original Dataframe
            for column_name in transformed_output.columns:
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

            return result_df

        elif isinstance(df_or_series, pd.Series):
            # Integrate values back into original Series
            series = integrate_masked_series(df_or_series,
                                             transformed_output,
                                             mask)
            return series

        else:
            raise TypeError('Expected DataFrame or Series input, not: {}'.format(type(df_or_series)))

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
        if self.inverse_operation:
            desc += ', and apply ({}) to inverted mask'.format(self.inverse_operation)
        return desc

    def short_description(self):
        return 'Apply operation on input with mask condition ({})'.format(self.condition)


class Where(Operation):
    """
    Implements conditional logic
    Created for test purposes - better to use Conditional which is more flexible and better performance
    """
    def __init__(self, condition, true_operation, false_operation):
        """

        :param condition: Callable which takes Dataframe or column and returns boolean series mask
        :param true_operation: Operation to pass masked column to
        :param false_operation: Optional operation to apply to data from inverted mask
        """
        super().__init__()
        self.true_operation = self.add_child_operation(true_operation)
        self.condition = self.add_child_operation(condition)
        self.false_operation = self.add_child_operation(false_operation)

    def action(self, df_or_series):
        """

        :param pd.DataFrame df_or_series:
        :return:
        """
        mask = self.condition(df_or_series)
        # Perform mask validation

        true_values = self.true_operation(df_or_series)
        # Perform validation

        false_values = self.false_operation(df_or_series)

        return true_values.where(mask, false_values)


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
