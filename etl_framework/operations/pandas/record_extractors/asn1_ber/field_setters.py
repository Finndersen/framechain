"""
Objects which define logic for aggregating multiple field values in case of SEQUENCE OF
"""
from etl_framework.exceptions import ETLFieldError


class BaseFieldSetter(object):
    """
    Base class for field setter which defines logic for how field values are set and aggregated when there are multiple
    (for when field occurs multiple times, e.g. in SEQUENCE OF)
    """
    def add_to_record(self, record, field_name, value):
        """
        Logic for adding new value to field. Value is initialised if there is no existing value, otherwise will be
        aggregated with existing value
        :param dict record:
        :param str field_name:
        :param value:
        :return:
        """
        if field_name in record:
            record[field_name] = self.get_aggregate_value(record[field_name], value)
        else:
            record[field_name] = self.get_initial_value(value)

    def get_initial_value(self, initial_value):
        """
        Behavior to initialise field value with first occurence
        :param initial_value:
        :return: Initialised value for field
        """
        raise NotImplementedError()

    def get_aggregate_value(self, existing_value, new_value):
        """
        Behaviour for aggregating field value with existing
        :param new_value:
        :return: New aggregated value for field
        """
        raise NotImplementedError()


class NoAggregation(BaseFieldSetter):
    """
    Aggregator which does not support aggregation - error is raised if multiple values received for field
    """
    def get_initial_value(self, initial_value):
        return initial_value

    def get_aggregate_value(self, existing_value, new_value):
        raise ETLFieldError('Aggregation not supported')


class SumAggregator(BaseFieldSetter):
    """
    Aggregator which sums or concatenates values
    """
    def get_initial_value(self, initial_value):
        return initial_value

    def get_aggregate_value(self, existing_value, new_value):
        """
        Behaviour for aggregating field value with existing
        :param new_value:
        :return: New aggregated value for field
        """
        return existing_value + new_value


class ListAggregator(BaseFieldSetter):
    """
    Aggregator which creates sequence/list of values and appends new one
    """
    def get_initial_value(self, initial_value):
        """
        Initialise list with single value
        :param initial_value:
        :return:
        """
        return [initial_value]

    def get_aggregate_value(self, existing_value, new_value):
        """
        Append new value to list
        :param existing_value:
        :param new_value:
        :return:
        """
        existing_value.append(new_value)
        return existing_value


class SetAggregator(BaseFieldSetter):
    """
    Aggregator which creates set of unique values
    """

    def get_initial_value(self, initial_value):
        """
        Initialise list with single value
        :param initial_value:
        :return:
        """
        return {initial_value}

    def get_aggregate_value(self, existing_value, new_value):
        """
        Append new value to list
        :param existing_value:
        :param new_value:
        :return:
        """
        existing_value.add(new_value)
        return existing_value