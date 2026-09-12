class SkipValues(object):
    """
    Used to skip certain byte values e.g. blanks, newlines
    """
    def __init__(self, values):
        if not all(isinstance(val, int) for val in values):
            raise ValueError('Provided values should be integers, not: {}'.format(values))
        self.values = set(values)

    def __call__(self, data, index):
        """
        Skip blank/null data and newlines
        :param data:
        :param index:
        :return:
        """
        while data[index] in self.values:
            index += 1

        return index


