from etl_framework.operations.base import Operation
from etl_framework.exceptions import MissingFieldError
import logging

log = logging.getLogger(__name__)


class BaseDataframeExporter(Operation):
    """
    Base class for operation which takes dataframe and converts or exports to some kind of output format
    """

    def __init__(self, create_for_empty=True, columns=None):
        """

        :param create_for_empty: Whether to create output file when dataframe is empty
        :param sequence columns: sequence of field names to export
        """
        super().__init__()
        self.create_for_empty = create_for_empty
        self.columns = columns

    def action(self, dataframe):
        # Return nothing if dataframe is empty
        if dataframe.empty and not self.create_for_empty:
            log.debug('DataFrame is empty, not creating any output')
            return None
        log.debug('Generating output from DataFrame (preview):\n{}\n{}'.format(dataframe.head(10), dataframe.dtypes))
        # Verify all desired output columns are in dataframe
        if self.columns:
            for column in self.columns:
                if column not in dataframe.columns:
                    self.error(MissingFieldError, 'Dataframe is missing expected output column: "{}"'.format(column))
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