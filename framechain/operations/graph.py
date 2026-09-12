from framechain.operations import Operation
from framechain.utils import randomstring


class SubGraph(Operation):
    """
    Operation which creates a labelled subgraph around the wrapped operations
    Does not actually perform any action during pipeline execution
    """
    def __init__(self, label, operation):
        """

        :param str label: Label for Subgraph
        :param Operation operation: Operation to wrap in subgraph
        """
        super().__init__()
        self.operation = self.add_child_operation(operation)
        self.label = label

    def action(self, *args):
        return self.operation(*args)

    def description(self):
        return self.operation.description()

    def short_description(self):
        return self.operation.short_description()

    def add_to_graph(self, graph):
        # Create Subgraph/cluster to contain wrapped operation
        from pydot import Cluster
        subgraph = Cluster(graph_name=randomstring(10), label=self.label)
        start_node, end_node = self.operation.add_to_graph(subgraph)
        graph.add_subgraph(subgraph)
        return start_node, end_node
