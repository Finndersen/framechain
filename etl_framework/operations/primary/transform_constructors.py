from etl_framework.operations.misc import Field
from etl_framework.utils import validate_callable
from etl_framework.operations.base import WrappingTypeTranslatorMixin
from etl_framework.operations.conditions import IsNull
from etl_framework.exceptions import ETLConfigurationError
from .base import PrimaryOperation
import pandas as pd


class CreateField(PrimaryOperation, WrappingTypeTranslatorMixin):
    """
    Create a new column/field using a transformation operation
    Can provide a conditional operation which is used to create a mask
    """
    calling_translations=wrapping_translations = {'dataframe': 'dataframe'}

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
            raise ValueError('Condition: {} must return a boolean Series'.format(self.condition))
        # Get Masked/filtered version of Dataframe
        transform_input = self.get_transform_input(dataframe, mask)
        # Perform transformation on dataframe
        output_series = self.transform(transform_input)#.copy())
        if not isinstance(output_series, pd.Series):
            raise ValueError('Transform: {} does not return a Series'.format(self.transform))
        # Add output Series back into original dataframe
        if mask is not None:
            dataframe.loc[mask, self.output_field] = output_series
        else:
            dataframe[self.output_field] = output_series

        return dataframe

    def get_transform_input(self, dataframe, mask):
        """
        Mask entire dataframe if appropriate
        """
        return dataframe[mask] if mask is not None else dataframe

    def __str__(self):
        rep = 'Create field "{}" using transform: {}'.format(self.output_field, self.transform)
        if self.condition:
            rep = rep + ' with condition: {}'.format(self.condition)
        return  rep


class ConvertField(CreateField):
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
            condition = Field(field)>>~IsNull()
        # Validate condition is not provided if transform changes data type of column
        if changes_type and condition:
            raise ETLConfigurationError('Should not define condition for {} because it changes column data type'.format(column_transform))
        super().__init__(field, column_transform, condition)

    def get_transform_input(self, dataframe, mask):
        """
        Only apply mask to target column (not whole dataframe)
        :param dataframe:
        :param mask:
        :return: potentially masked Series of target field
        """
        return dataframe.loc[mask, self.output_field] if mask is not None else dataframe[self.output_field]

    def __str__(self):
        return 'Convert field "{}" using transform: {} with condition: {}'.format(self.output_field, self.transform, self.condition)

