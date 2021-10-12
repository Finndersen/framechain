from etl_framework.operations import Operation


class DataframeOperation(Operation):
    """
    Abstract base class for a primary pandas ETL operation (highest level)
    A configurable callable which takes DataFrame,  performs some kind of processing, and returns DataFrame
    """

    def action(self, dataframe):
        raise NotImplementedError()


class ColumnOperation(Operation):
    """
    Base Class for operations that operate on one or more columns to perform vectorised condition logic and return single Series
    Could be transforms, conditionals or converters
    Use 'SelectField' operation or 'OnField' or 'MapFields' wrappers to supply individual column(s) from dataframe
    """

    def action(self, *args):
        """
        Take one or more columns or scalar values
        :return: series
        """
        raise NotImplementedError()
