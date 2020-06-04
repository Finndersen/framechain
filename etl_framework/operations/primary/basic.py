from .base import PrimaryOperation
from logging import getLogger
from etl_framework.utils import validate_callable, LogDuration
from etl_framework.exceptions import ValidationError
import pandas as pd
import copy


log = getLogger(__name__)


class DeleteRows(PrimaryOperation):
    """
    Operation used to filter DF on provided condition
    """
    def __init__(self, condition):
        """
        :param callable condition: Condition to filter row on. Takes DF and returns boolean mask
        """
        self.condition = validate_callable(condition, wrap_scalar=False)

    def __call__(self, dataframe):
        filtered_df = dataframe.loc[~self.condition(dataframe)]
        log.debug('Filtered out {} rows ({} remaining)'.format(len(dataframe.index) - len(filtered_df.index), len(filtered_df.index)))
        return filtered_df

    def __str__(self):
        return 'Filter out rows which match condition: {}'.format(self.condition)


class DropColumns(PrimaryOperation):
    """
    Used to drop columns from dataframe
    """
    def __init__(self, columns):
        """

        :param str/list columns: single column name or list of column names
        """
        self.columns = columns

    def __call__(self, dataframe):
        return dataframe.drop(self.columns, axis=1)

    def __str__(self):
        return 'Drop columns: {}'.format(self.columns)


class RenameColumns(PrimaryOperation):
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


class Sort(PrimaryOperation):
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


class Validate(PrimaryOperation):
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
            raise ValueError('Condition: {} must return a boolean Series'.format(self.validation_condition))
        validation_fails = ~validation_result
        fail_count = validation_fails.sum()
        if fail_count:
            raise ValidationError('{} records failed validation: {}. Examples:\n{}'.format(fail_count,
                                                                                           self.message,
                                                                                           dataframe[validation_fails].head()))

    def __str__(self):
        return 'Validate: {}'.format(self.message)


class Fork(PrimaryOperation):
    """
    Transformation which allows creating a fork in the execution pipeline
    Causes input value (e.g. DataFrame) to be copied and provided to multiple operation chains
    Will return a list containing outputs of each operation chain
    Each chain should end in an Output Generator because it can be cumbersome to aggregate or do further
    processing on the output sequence from this operation
    """
    def __init__(self, *operation_chains):
        """

        :param operation_chains: Sequence of operation chains to execute with single input. Each item can be a list of
        operations, or a single operation (potentially a chain of operations using >> operator)
        """
        self.operation_chains = [op_chain if isinstance(op_chain, (tuple, list)) else [op_chain]
                                 for op_chain in operation_chains]

    def __call__(self, input_val):
        """

        :param input_val: Input value to provide to all operation chains (e.g. pd.Dataframe instance)
        :return:
        """
        outputs = []

        # Execute chain of operations (TODO: initialise new Pipeline instance to handle this?)
        for i, op_chain in enumerate(self.operation_chains):
            value = copy.deepcopy(input_val)
            for operation in op_chain:
                with LogDuration(log, 'Running fork #{} operation: {}'.format(i, operation)):
                    value = operation(value)
            outputs.append(value)
        return outputs

    def __str__(self):
        return 'Fork into chains: {}'.format('\n'.join('#{}: ({})'.format(i,
                                                                          ','.join('({})'.format(str(op)) for op in op_chain))
                                                       for i, op_chain in enumerate(self.operation_chains)))