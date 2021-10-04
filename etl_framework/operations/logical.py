from etl_framework.operations import Operation


class In(Operation):
    """
    Used to implement 'in' operator
    """

    def __init__(self, collection):
        """

        :param collection: Collection of values or object to test if value is included in
        """
        super().__init__()
        self.collection = collection

    def action(self, value):
        return value in self.collection

    def description(self):
        return 'Value is in: {}'.format(self.collection)


class Is(Operation):
    """
    Used to implement 'is' operator
    """

    def __init__(self, other_value):
        """

        :param other_value: Other value to compare to
        """
        super().__init__()
        self.other_value = other_value

    def action(self, value):
        return value is self.other_value

    def description(self):
        return 'Value is: {}'.format(self.other_value)


class And(Operation):
    """
    Evaluate 'and' statement on results of wrapped operations
    """
    def __init__(self, *operations):
        """
        Operations to have outputs AND'd together
        :param operations:
        """
        super().__init__()
        if len(operations) < 2:
            raise ValueError('"And" operation must be provided with at least 2 operations')
        for operation in operations:
            self.add_child_operation(operation)

    def action(self, *args, **kwargs):
        # Initialise with first result
        value = self.run_child_operation(self.child_operations[0], *args, **kwargs)
        for operation in self.child_operations[1:]:
            # Exit early if falsey
            if not value:
                break

            value = value and self.run_child_operation(operation, *args, **kwargs)

        return value


class Or(And):
    """
    Evaluate 'or' statement on results of wrapped operations
    """

    def action(self, *args, **kwargs):
        # Initialise with first result
        value = self.run_child_operation(self.child_operations[0], *args, **kwargs)
        for operation in self.child_operations[1:]:
            # Exit early if truthy
            if value:
                break

            value = value or self.run_child_operation(operation, *args, **kwargs)

        return value


class Not(Operation):
    """
    Performs Not operator.
    """
    def __init__(self, operation):
        """

        :param operation: Operation to wrap and return NOT result of.
        """
        super().__init__()
        self.operation = self.add_child_operation(operation)

    def action(self, *args, **kwargs):
        return not self.run_child_operation(self.operation, *args, **kwargs)

    def description(self):
        return 'NOT ({})'.format(self.operation)