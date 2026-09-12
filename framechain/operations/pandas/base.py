from framechain.operations import Operation


class DataframeOperation(Operation):
    """
    Base class for operations that expect a DataFrame as input
    """
    ALL_COLUMNS = object()
    NO_COLUMNS = object()

    def get_required_columns(self):
        """
        Return list of DataFrame columns required for this operation
        :return:
        """
        return self.ALL_COLUMNS


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
