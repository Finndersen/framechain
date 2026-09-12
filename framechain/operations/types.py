from framechain.exceptions import UnsupportedOperatorError


class TypeTranslations(object):
    """
    Class which holds base configurations and helper methods relating to type translations
    """
    TYPE_HIERARCHY = {
        'dataframe': 3,
        'column': 2,
        'row': 2,
        'value': 1
    }

    # Generic type translation and compatability
    GENERIC_TYPE_TRANSLATIONS = {
        'dataframe': 'dataframe',
        'row': 'row',
        'column': 'column',
        'value': 'value',
    }

    @classmethod
    def get_for_operation(cls, operation):
        """
        Get defined calling type translations of operation, or generic defaults if not specified
        :param operation:
        :return:
        """
        return getattr(operation, 'calling_translations', cls.GENERIC_TYPE_TRANSLATIONS)

    @staticmethod
    def check_operator_allowed(operation, operator_str):
        """
        Checks whether the provided operation is compatible with operators (must return column or value type)
        :param operation:
        :return:
        """
        output_types = set(getattr(operation, 'calling_translations', {'placeholder': 'column'}).values())
        if not output_types.intersection({'column', 'value'}):
            raise UnsupportedOperatorError('Operation: {} does not support operator: {}'.format(operation, operator_str))