from etl_framework.operations.base import BaseOperation


class BaseOutputGenerator(BaseOperation):
    """
    Base class for output generators
    Callable which takes final dataframe and produces some kind of output (write file, insert database, etc)
    Returns something relevant to output (e.g. output file object)
    """
    calling_translations = {'dataframe': 'output'}

    def __init__(self, create_for_empty=True):
        """

        :param create_for_empty: Whether to create output file when dataframe is empty
        """
        self.create_for_empty = create_for_empty

    def __call__(self, dataframe):
        # Return nothing if dataframe is empty
        if dataframe.empty and not self.create_for_empty:
            return None
        # Generate output
        generate_result = self.generate_output(dataframe)
        return self.get_return_value(generate_result)

    def generate_output(self, dataframe):
        """
        Generate output using transformed dataframe (output to file, database, etc..)
        :param dataframe:
        :return:
        """
        raise NotImplementedError()

    def get_return_value(self, generate_result):
        """
        Get return value corresponding to output (filename, number of rows inserted, etc..)
        :param generate_result: return value of generate_output() method
        :return:
        """
        return generate_result