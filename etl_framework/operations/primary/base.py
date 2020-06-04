from etl_framework.operations.base import  BaseOperation


class PrimaryOperation(BaseOperation):
    """
    Abstract base class for a primary ETL operation (highest level)
    A configurable callable which takes DataFrame,  performs some kind of processing, and returns DataFrame
    Are chainable but do not support other operators
    """
    calling_translations = {'dataframe': 'dataframe'}

    def __call__(self, dataframe):
        raise NotImplementedError()