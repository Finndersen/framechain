"""
Operations which are used to help construct more complex field-based transforms with masking capability
"""
import pandas as pd
import numpy as np
from pandas.api.types import is_datetime64_any_dtype, is_categorical_dtype

from etl_framework.exceptions import ChangedDataTypError, ETLConfigurationError
from etl_framework.operations import Operation
from etl_framework.operations.pandas import Field, IsNull, ConditionallyAppliedOperation


class SetColumn(ConditionallyAppliedOperation):
    """
    Set a column/field values using a transformation operation. Creates new column if doesnt already exist in DataFrame
    Can provide a conditional operation which is used to create a mask
    """

    def __init__(self, field, transform, condition=None):
        """
        :param str field: Name of column to populate output values in
        :param callable transform: Callable which takes Dataframe and returns Series.
        :param callable condition: callable which takes dataframe and returns a boolean series mask.
        """
        super().__init__(transform, condition=condition)
        self.field = field

    def action(self, dataframe):
        """
        Perform transformation on dataframe
        :param DataFrame dataframe:
        :return:
        """
        # Make shallow copy so changes arent made to original DF
        dataframe = dataframe.copy(deep=False)
        # Get transform mask
        mask = self.get_mask(dataframe)
        # Exit early if mask does not match any values (no changes made)
        if mask is not None and not mask.any():
            # Add empty column if doesnt exist
            if self.field not in dataframe.columns:
                dataframe[self.field] = np.nan
            return dataframe

        # Get Masked/filtered version of Dataframe
        transform_input = self.get_transform_input(dataframe, mask)
        # Perform transformation on dataframe
        output_series = self.run_child_operation(self.operation, transform_input)
        if not isinstance(output_series, pd.Series):
            self.error(ValueError,
                       'Transform: {} returns: "{}", not return a Series'.format(self.operation, type(output_series)))

        # Add output Series back into original dataframe
        if mask is not None:
            # Perform checks if integrating with existing column
            if self.field in dataframe.columns:
                # Raise error if datetime dtype of column has changed (can cause issues with timezone mismatch)
                if (dataframe[self.field].dtype != output_series.dtype and
                        is_datetime64_any_dtype(dataframe[self.field].dtype)):
                    raise ChangedDataTypError(
                        'Operation: "{}" changes datetime datatype of masked values from "{}" to "{}", which may have undesired effect. '
                        'Removing any conditions may resolve the issue'.format(self.operation,
                                                                               dataframe[self.field].dtype,
                                                                               output_series.dtype))

                # If merging with existing Category column, need to align categories
                if is_categorical_dtype(dataframe[self.field]):
                    output_series = output_series.astype('category')
                    all_categories = dataframe[self.field].cat.categories.union(output_series.cat.categories)
                    dataframe[self.field] = dataframe[self.field].cat.set_categories(all_categories)
                    output_series = output_series.cat.set_categories(all_categories)

            # Need to use .loc with mask to not overwrite existing values
            dataframe.loc[mask, self.field] = output_series
        else:
            dataframe[self.field] = output_series

        return dataframe

    def get_transform_input(self, dataframe, mask):
        """
        Mask entire dataframe if appropriate
        """
        return dataframe[mask] if mask is not None else dataframe

    def short_description(self):
        rep = 'Set column "{}"'.format(self.field)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return rep

    def description(self):
        rep = 'Set column "{}" value using transform: {}'.format(self.field, self.operation)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return rep


class ConvertColumn(SetColumn):
    """
    Apply a conversion operation to a single existing column
    """
    wrapping_translations = {'dataframe': 'column'}

    def __init__(self, field, column_transform, condition=None, ignore_null=False):
        """
        :param str field: name of field to convert
        :param column_transform:  Callable which performs transform operation on series and returns transformed series
        :param str input_field: name of field/column to supply to transform function. (defaults to output field)
        :param callable condition: callable which takes dataframe and returns a filter mask.
        :param bool ignore_null: Whether to add condition to mask out null values if condition is not provided
        If not specified, NotNull condition will be applied. Set to False to disable
        """
        super().__init__(field, column_transform, condition)
        changes_type = getattr(column_transform, 'changes_type', False)
        # Add NotNull filter condition
        if not condition and not changes_type and ignore_null:
            condition = Field(field) >> ~IsNull()
        # Validate condition is not provided if transform changes data type of column
        if changes_type and condition:
            self.error(ETLConfigurationError,
                       'Should not define condition for {} because it changes column data type'.format(
                           column_transform))

    def get_transform_input(self, dataframe, mask):
        """
        Only apply mask to target column (not whole dataframe)
        :param dataframe:
        :param mask:
        :return: potentially masked Series of target field
        """
        # Verify column already exists
        if self.field not in dataframe.columns:
            raise KeyError('Field: "{}" does not exist in DataFrame'.format(self.field))
        return dataframe.loc[mask, self.field].copy() if mask is not None else dataframe[self.field]

    def short_description(self):
        rep = 'Convert column "{}"'.format(self.field)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return rep

    def description(self):
        return 'Convert column "{}" using transform: {} with condition: {}'.format(self.field, self.operation,
                                                                                  self.condition)


class ConvertColumns(ConditionallyAppliedOperation):
    """
    Select a subset of columns from a DataFrame to apply operations to.
    Initialise with transform which is provided this subset dataframe and returns a transformed dataframe with same
    number of columns.
    Allows for better performance of operations applied to entire DF (e.g. Apply, FillNA) when only subset of fields
    are required
    """
    def __init__(self, fields, transform, condition=None):
        """
        :param list fields: List of column names to select to create subset dataframe
        :param callable transform: Callable which takes Dataframe and returns Dataframe of same size
        :param callable condition: callable which takes dataframe  and returns a boolean series mask.
        """
        super().__init__(transform, condition=condition)
        if not isinstance(fields, (list, tuple)):
            raise TypeError('Fields must be provided as list or tuple')
        self.fields = fields

    def action(self, dataframe):

        # Get conditional mask
        mask = self.get_mask(dataframe)
        # Exit early if mask does not match any values (no changes made)
        if mask is not None and not mask.any():
            return dataframe

        transform_input = dataframe.loc[mask, self.fields] if mask is not None else dataframe[self.fields]
        output_subset_df = self.run_child_operation(self.operation, transform_input)
        # Make shallow copy so changes arent made to original DF
        output_dataframe = dataframe.copy(deep=False)
        if mask is None:
            output_dataframe[self.fields] = output_subset_df
        else:
            output_dataframe.loc[mask, self.fields] = output_subset_df

        return output_dataframe


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
        row[self.field] = self.run_child_operation(self.transform, row)
        return row

    def short_description(self):
        return 'Set field "{}"'.format(self.field)

    def description(self):
        return 'Set field "{}" value using transform: {}'.format(self.field, self.transform)