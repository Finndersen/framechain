from etl_framework.operations import Operation
from etl_framework.utils import randomstring


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
    calling_translations = {'column': 'column'}

    # Whether the operation can change the DTYPE of the column. Used by ConvertField to decide whether to apply condition
    changes_type = False

    def action(self, *args, **kwargs):
        """
        Take one or more columns or scalar values
        :return: series
        """
        raise NotImplementedError()


class ConditionallyAppliedOperation(Operation):
    """
    Base class for transform constructors which take an operation and apply it to a masked subset of the input
    dataframe using a provided conditional operation
    """
    def __init__(self, operation, condition=None):
        """

        :param Operation operation: Operation to apply
        :param Operation condition: will be provided input dataframe, and return boolean series mask which determines
        which rows 'operation' will be applied to (optional)
        """
        super().__init__()
        self.operation = self.wrap_operation(operation)
        self.condition = self.wrap_operation(condition, none_allowed=True)

    def add_to_graph(self, graph):
        # Create Subgraph/cluster to contain wrapped operation
        from pydot import Subgraph, Cluster
        subgraph = Cluster(graph_name=randomstring(10), label=self.short_description())
        start_node, end_node = self.operation.add_to_graph(subgraph)
        graph.add_subgraph(subgraph)
        return start_node, end_node
