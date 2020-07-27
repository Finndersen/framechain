import logging
from etl_framework.utils import LogDuration, ConfigurableClass
from etl_framework.context import set_context

log = logging.getLogger(__name__)


class ETLProcessor(ConfigurableClass):
    """
    Base class for ETL Processor, tailored towards pandas/dataframe pipelines
    Performs end-to-end ETL processing record extraction, transformation to output generation
    """
    # Input Reader - Callable which takes input parameter and returns data for Record Extractor
    input_reader = None
    # Record extractor - Callable which takes raw file/record data and returns Data Frame containing values in native types
    record_extractor = None
    # List/Tuple of operations to apply on dataframe (can be transforms, filters, validation). Each one is passed dataframe and returns a new one
    operations = []
    # Callable which takes input parameter and final dataframe and produces an output. Returns value associated with output (e.g. output file object)
    output_generator = None

    def run(self, etl_input):
        """

        :param etl_input: Input to ETL processor, type depends on requirements of Record Extractor
        :return:
        """
        with LogDuration(log,'Running {} with input: {}'.format(type(self).__name__, etl_input)):

            set_context(self.get_context(etl_input))

            input_reader = self.get_input_reader(etl_input)
            record_extractor = self.get_record_extractor(etl_input)

            # Extract records
            with LogDuration(log, 'Building dataframe from input...'):
                dataframe = (input_reader >> record_extractor)(etl_input)

            if dataframe.empty:
                log.debug('No valid records extracted')
            else:
                # Display head of initial dataframe
                log.debug('Extracted {} records: \n{}\n{}'.format(len(dataframe.index), dataframe.head(10), dataframe.dtypes))
                # Perform operations
                dataframe = self._run_operations(etl_input, dataframe)

            # Create output/export from records
            return self._get_result(etl_input, dataframe)

    def get_context(self, etl_input):
        """
        Set any desired transform context data (e.g. file info, lookup data, dynamic config..)
        :param etl_input:
        :return:
        """
        return {}

    def get_input_reader(self, etl_input):
        """
        Get Record Extractor callable. If configuration should vary with input value, create record extractor in this method
        :param etl_input:
        :return:
        """
        return self.input_reader

    def get_record_extractor(self, etl_input):
        """
        Get Record Extractor. If configuration should vary with input value, create record extractor in this method
        :param etl_input:
        :return:
        """
        return self.record_extractor

    def get_operations(self, etl_input):
        """
        Get list of transformation operations
        :param etl_input:
        :return:
        """
        return self.operations

    def get_output_generator(self, etl_input):
        """
        Get output generator callable. If configuration should vary with input value, create output generator in this method
        :param etl_input:
        :return:
        """
        return self.output_generator

    def _run_operations(self, etl_input, dataframe):
        """
        Perform transformation operations on dataframe
        :param etl_input: ETL input parameter
        :param dataframe:
        :return:
        """
        operations = self.get_operations(etl_input)
        for operation in operations:
            # Exit if dataframe is empty
            if dataframe.empty:
                log.debug("Dataframe is now empty, skipping remaining operations")
                break

            # Run operation
            with LogDuration(log, 'Running operation: {}'.format(operation)):
                dataframe = operation(dataframe)
                log.debug(dataframe.head())

        return dataframe

    def _get_result(self, etl_input, dataframe):
        """
        Create output from final dataframe
        :param etl_input: input provided to ETL processor
        :param dataframe:
        :return:
        """
        output_generator = self.get_output_generator(etl_input)
        with LogDuration(log, 'Generating output...'):
            result = output_generator(dataframe)
        return result

