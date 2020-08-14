"""
Primary Pandas operations which take Dataframe and return Dataframe
"""
import pandas as pd
from etl_framework.exceptions import ValidationError, ETLConfigurationError, ChangedDataTypError
from etl_framework.operations.pandas import Field, IsNull
from etl_framework.operations.base import BaseOperation, WrappingTypeTranslatorMixin
import logging
from etl_framework.utils import validate_callable

log = logging.getLogger(__name__)


class DataframeOperation(BaseOperation):
    """
    Abstract base class for a primary pandas ETL operation (highest level)
    A configurable callable which takes DataFrame,  performs some kind of processing, and returns DataFrame
    Are chainable but do not support other operators
    """
    calling_translations = {'dataframe': 'dataframe'}

    def __call__(self, dataframe):
        raise NotImplementedError()


class SetColumn(DataframeOperation, WrappingTypeTranslatorMixin):
    """
    Set a column/field values using a transformation operation. Creates new column if doesnt already exist in DataFrame
    Can provide a conditional operation which is used to create a mask
    """
    calling_translations = wrapping_translations = {'dataframe': 'dataframe'}

    def __init__(self, output_field, transform, condition=None):
        """
        :param str output_field: Name of column to populate output values in
        :param callable transform: Callable which either takes Dataframe or Series and returns Series. Can be result of chaining multiple Transform components togehter
        :param callable condition: callable which takes dataframe  and returns a boolean series mask. Ideally use sublcass of BaseVectorMask which can be chained with bitwise operators
        """
        self.validate_wrapped_operation_compatability(transform)
        self.transform = validate_callable(transform)
        self.output_field = output_field
        self.condition = validate_callable(condition, wrap_scalar=False)
        self.context = None

    def __call__(self, dataframe):
        """
        Perform transformation on dataframe
        :param DataFrame dataframe:
        :return:
        """
        # Generate transform mask with condition if appropriate
        mask = self.condition(dataframe) if self.condition else None
        if mask is not None and not (isinstance(mask, pd.Series) and str(mask.dtype) == 'bool'):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.condition))
        # Get Masked/filtered version of Dataframe
        transform_input = self.get_transform_input(dataframe, mask)
        # Perform transformation on dataframe
        output_series = self.transform(transform_input)
        if not isinstance(output_series, pd.Series):
            self.error(ValueError,
                       'Transform: {} returns: "{}", not return a Series'.format(self.transform, type(output_series)))
        # Add output Series back into original dataframe
        if mask is not None:
            # Raise error if dtype of column has changed, can have undesired effect
            if (self.output_field in dataframe.columns
                    and dataframe[self.output_field].dtype != 'object'
                    and dataframe[self.output_field].dtype != output_series.dtype):
                raise ChangedDataTypError(
                    'Operation: "{}" changes datatype of masked values from "{}" to "{}", which may have undesired effect. '
                    'Removing any conditions may resolve the issue'.format(self.transform,
                                                                           dataframe[self.output_field].dtype,
                                                                           output_series.dtype))
            dataframe.loc[mask, self.output_field] = output_series
        else:
            dataframe[self.output_field] = output_series

        return dataframe

    def get_transform_input(self, dataframe, mask):
        """
        Mask entire dataframe if appropriate
        """
        return dataframe[mask].copy() if mask is not None else dataframe

    def __str__(self):
        rep = 'Create field "{}" using transform: {}'.format(self.output_field, self.transform)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return rep


class ConvertColumn(SetColumn):
    """
    Apply a conversion operation to a single column
    """
    wrapping_translations = {'dataframe': 'column'}

    def __init__(self, field, column_transform, condition=None, ignore_null=True):
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
        return dataframe.loc[mask, self.output_field].copy() if mask is not None else dataframe[self.output_field]

    def __str__(self):
        return 'Convert field "{}" using transform: {} with condition: {}'.format(self.output_field, self.transform,
                                                                                  self.condition)


class DeleteRows(DataframeOperation):
    """
    Operation used to filter DF on provided condition
    """

    def __init__(self, condition):
        """
        :param callable condition: Condition to filter row on. Takes DF and returns boolean mask
        """
        self.condition = validate_callable(condition, wrap_scalar=False)

    def __call__(self, dataframe):
        # Get masked/filtered DF
        filtered_df = dataframe.loc[~self.condition(dataframe)]
        log.debug('Filtered out {} rows ({} remaining)'.format(len(dataframe.index) - len(filtered_df.index),
                                                               len(filtered_df.index)))
        # Return copy so that it is not a slice (which may raise SettingWithCopyWarning)
        return filtered_df.copy()

    def __str__(self):
        return 'Filter out rows which match condition: {}'.format(self.condition)


class DropColumns(DataframeOperation):
    """
    Used to drop columns from dataframe
    """

    def __init__(self, columns, errors='ignore'):
        """

        :param str/list columns: single column name or list of column names
        :param str errors: action for handling errors
        """
        self.columns = columns
        self.errors = errors

    def __call__(self, dataframe):
        return dataframe.drop(self.columns, errors=self.errors, axis=1)

    def __str__(self):
        return 'Drop columns: {}'.format(self.columns)


class RenameColumns(DataframeOperation):
    """
    Operation for renaming columns
    """

    def __init__(self, **rename_mapping):
        """

        :param str rename_mapping: mapping of old column names to new ones
        """
        self.rename_mapping = rename_mapping

    def __call__(self, dataframe):
        return dataframe.rename(columns=self.rename_mapping)

    def __str__(self):
        return 'Rename columns: {}'.format(self.rename_mapping)


class Sort(DataframeOperation):
    """
    Sort dataframe by columns
    """

    def __init__(self, sort_by, ascending=True):
        """

        :param sort_by: Name or list of names to sort by
        """
        self.sort_by = sort_by
        self.ascending = ascending

    def __call__(self, dataframe):
        return dataframe.sort_values(self.sort_by, ascending=self.ascending)

    def __str__(self):
        return 'Sort by: {}'.format(self.sort_by)


class Validate(DataframeOperation):
    """
    Raise exception if any rows do not match specified validation condition
    """

    def __init__(self, validation_condition, message=None):
        """

        :param validation_condition: callable which takes dataframe and returns Boolean Series
        :param message: Message describing validation condition
        """
        self.validation_condition = validation_condition
        self.message = message or str(validation_condition)

    def __call__(self, dataframe):
        # Perform validation
        validation_result = self.validation_condition(dataframe)
        if not (isinstance(validation_result, pd.Series) and str(validation_result.dtype) == 'bool'):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.validation_condition))
        validation_fails = ~validation_result
        fail_count = validation_fails.sum()
        if fail_count:
            self.error(ValidationError, '{} records failed validation: {}. Examples:\n{}'.format(fail_count,
                                                                                                 self.message,
                                                                                                 dataframe[
                                                                                                     validation_fails].head()))

    def __str__(self):
        return 'Validate: {}'.format(self.message)


class FillColumnsNA(DataframeOperation):
    """
    Fill NA values of specified columns with particular value
    """

    def __init__(self, columns, value):
        """
        :param str/list columns: List of column names or single column name
        :param value: static value or callable which returns scalar value
        """
        self.value = value
        if isinstance(columns, str):
            columns = [columns]
        self.columns = columns

    def __call__(self, dataframe):
        """

        :param dataframe: Dataframe or Series
        :return:
        """
        fill_value = self.value(dataframe) if callable(self.value) else self.value
        for column_name in self.columns:
            dataframe[column_name].fillna(fill_value)
        return dataframe

    def __str__(self):
        return 'Fill columns {} NA values with: "{}"'.format(self.columns, self.value)
