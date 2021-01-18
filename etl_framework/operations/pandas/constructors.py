"""
Operations which are used to help construct more complex field-based transforms with masking capability
"""
import pandas as pd
from pandas.core.dtypes.common import is_datetime64_any_dtype

from etl_framework.exceptions import ChangedDataTypError, ETLConfigurationError
from etl_framework.operations.base import WrappingTypeTranslatorMixin
from etl_framework.operations.pandas import Field, IsNull
from etl_framework.operations.pandas.base import ConditionallyAppliedOperation


class SetColumn(ConditionallyAppliedOperation, WrappingTypeTranslatorMixin):
    """
    Set a column/field values using a transformation operation. Creates new column if doesnt already exist in DataFrame
    Can provide a conditional operation which is used to create a mask
    """
    calling_translations = wrapping_translations = {'dataframe': 'dataframe'}

    def __init__(self, field, transform, condition=None):
        """
        :param str field: Name of column to populate output values in
        :param callable transform: Callable which either takes Dataframe or Series and returns Series. Can be result of chaining multiple Transform components togehter
        :param callable condition: callable which takes dataframe  and returns a boolean series mask. Ideally use sublcass of BaseVectorMask which can be chained with bitwise operators
        """
        super().__init__(transform, condition=condition)
        self.field = field
        self.context = None

    def action(self, dataframe):
        """
        Perform transformation on dataframe
        :param DataFrame dataframe:
        :return:
        """
        # Generate transform mask with condition if appropriate
        mask = self.condition(dataframe) if self.condition else None
        if mask is not None and not pd.api.types.is_bool_dtype(mask):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))
        # Get Masked/filtered version of Dataframe
        transform_input = self.get_transform_input(dataframe, mask)
        # Perform transformation on dataframe
        output_series = self.operation(transform_input)
        if not isinstance(output_series, pd.Series):
            self.error(ValueError,
                       'Transform: {} returns: "{}", not return a Series'.format(self.operation, type(output_series)))
        # Add output Series back into original dataframe
        if mask is not None:
            # Raise error if datetime dtype of column has changed (can cause issues with timezone mismatch)
            if (self.field in dataframe.columns
                    and dataframe[self.field].dtype != output_series.dtype
                    and is_datetime64_any_dtype(dataframe[self.field].dtype)):
                raise ChangedDataTypError(
                    'Operation: "{}" changes datetime datatype of masked values from "{}" to "{}", which may have undesired effect. '
                    'Removing any conditions may resolve the issue'.format(self.operation,
                                                                           dataframe[self.field].dtype,
                                                                           output_series.dtype))
            dataframe.loc[mask, self.field] = output_series
        else:
            dataframe[self.field] = output_series

        return dataframe

    def get_transform_input(self, dataframe, mask):
        """
        Mask entire dataframe if appropriate
        """
        return dataframe[mask].copy() if mask is not None else dataframe

    def short_description(self):
        rep = 'Set field "{}"'.format(self.field)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return rep

    def description(self):
        rep = 'Set field "{}" value using transform: {}'.format(self.field, self.operation)
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
        :param column_transform:  Callable which performs transform operation. Will be passed single DF column, should return Series
        :param str input_field: name of field/column to supply to transform function. (defaults to output field)
        :param callable condition: callable which takes dataframe and returns a filter mask.
        :param bool ignore_null: Whether to add condition to mask out null values if condition is not provided
        If not specified, NotNull condition will be applied. Set to False to disable
        """
        changes_type = getattr(column_transform, 'changes_type', False)
        # Add NotNull filter condition
        if not condition and not changes_type and ignore_null:
            condition = Field(field) >> ~IsNull()
        # Validate condition is not provided if transform changes data type of column
        if changes_type and condition:
            self.error(ETLConfigurationError,
                       'Should not define condition for {} because it changes column data type'.format(
                           column_transform))
        super().__init__(field, column_transform, condition)

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
        rep = 'Convert field "{}"'.format(self.field)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return rep

    def description(self):
        return 'Convert field "{}" using transform: {} with condition: {}'.format(self.field, self.operation,
                                                                                  self.condition)