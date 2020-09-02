from etl_framework.operations.base import BaseOperation
from etl_framework.exceptions import ValidationError
import pandas as pd


class Validate(BaseOperation):
    """
    Perform validation on DataFrame or Column values
    Provide an conditional operation which takes a Dataframe or Column (Series) and returns a boolean series
    If any result values are not True, ValidationError will be raised
    Otherwise, pass through input value
    """
    calling_translations = {
        'dataframe': 'dataframe',
        'column': 'column'
    }

    def __init__(self, validation_condition, message=None):
        """

        :param validation_condition: callable which takes dataframe and returns Boolean Series
        :param message: Message describing validation condition
        """
        self.validation_condition = validation_condition
        self.message = message or str(validation_condition)

    def __call__(self, vector):
        # Perform validation
        validation_result = self.validation_condition(vector)
        if not pd.api.types.is_bool_dtype(validation_result):
            self.error(ValueError, 'Condition: {} must return a boolean Series'.format(self.validation_condition))
        validation_fails = ~validation_result
        fail_count = validation_fails.sum()
        if fail_count:
            self.error(ValidationError, '{} records failed validation: {}. Examples:\n{}'.format(fail_count,
                                                                                                 self.message,
                                                                                                 vector[validation_fails].head()))

    def __str__(self):
        return 'Validate: {}'.format(self.message)