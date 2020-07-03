from etl_framework.operations import BaseOperation


class DataframeOperation(BaseOperation):
    """
    Base class for operations that take entire dataframe and return single Series
    """
    calling_translations = {'dataframe': 'column'}

    def __call__(self, dataframe):
        """
        Take dataframe and return series
        :return: boolen series
        """
        raise NotImplementedError()


class ColumnOperation(BaseOperation):
    """
    Base Class for operations that operate on one or more columns to perform vectorised condition logic and return single Series
    Could be transforms, conditionals or converters
    Use 'SelectField' operation or 'OnField' or 'MapFields' wrappers to supply individual column(s) from dataframe
    """
    calling_translations = {'column': 'column'}

    # Whether the operation can change the DTYPE of the column. Used by ConvertField to decide whether to apply condition
    changes_type = False

    def __call__(self, *args, **kwargs):
        """
        Take one or more columns or scalar values
        :return: series
        """
        raise NotImplementedError()