import csv

import pandas as pd

from etl_framework.operations.pandas.record_extractors.base import InputField, BaseDataFrameGenerator, \
    TimestampFieldMixin, IntegerFieldMixin


class AdvancedDelimitedRecordExtractor(BaseDataFrameGenerator):
    """
    Alternative custom implementation of delimited (CSV) record extractor, to support case of files with different
    record types which may have different field specifications. Allows specifying the column index of a field on a per
    record type basis.
    Adds fields to indicate record type and original record number
    Should use standard DelimitedRecordExtractor if this functionality is not required (better performance)

    """
    RECORDTYPE_FIELD_NAME = '_record_type'
    RECORDNUMBER_FIELD_NAME = '_record_number'

    def __init__(self, fields, recordtype_detector, **csv_reader_kwargs):
        """

        :param list/tuple fields: Sequence of AdvancedCSVField
        :param recordtype_detector: Callable which takes raw record (list of values) and returns record type as string, or None if record should be skipped
        :param csv_reader_kwargs: kwargs to provide to csv.reader()
        """

        super().__init__(fields)
        self.recordtype_detector = self.wrap_operation(recordtype_detector)
        self.csv_reader_kwargs = csv_reader_kwargs

    def create_dataframe(self, file_reader):
        """

        :param file_reader: Text file reader of CSV file
        :return:
        """
        output_records = []
        csv_reader = csv.reader(file_reader, **self.csv_reader_kwargs)
        for record_number, raw_row in enumerate(csv_reader, start=1):
            recordtype = self.run_wrapped_operation(self.recordtype_detector, raw_row)

            # Skip record if no record type
            if recordtype is None:
                continue

            if not isinstance(recordtype, str):
                raise TypeError('Record Type must be a string, not: "{}"'.format(recordtype))

            record = [field.get_value(raw_row, recordtype) for field in self.fields] + [recordtype,
                                                                                        record_number]
            output_records.append(record)

        return pd.DataFrame(data=output_records,
                            columns=[field.name for field in self.fields] + [self.RECORDTYPE_FIELD_NAME,
                                                                             self.RECORDNUMBER_FIELD_NAME],
                            dtype='object')


class AdvancedCSVField(InputField):
    """
    Base field class for defining fields in CSV file. Field column IDs can be defined per record type using a dictionary,
    or constant value for all record types
    """

    def __init__(self, name, column_id, **kwargs):
        """

        :param str name: Field name
        :param int or dict column_id: Mapping of record type to column id, or constant value for all record types
        :param kwargs:
        """
        self.column_id = column_id
        super().__init__(name, **kwargs)

    def id_for_recordtype(self, recordtype):
        """
        Get csv field ID for record type
        :param str recordtype:
        :return:
        """
        if isinstance(self.column_id, int):
            return self.column_id

        return self.column_id.get(recordtype, None)

    def get_value(self, record, recordtype):
        """

        :param list record: Raw CSV record
        :param str recordtype: recordtype of record
        :return:
        """
        if isinstance(self.column_id, int):
            field_id = self.column_id
        else:
            field_id = self.column_id.get(recordtype, None)

        if field_id is None:
            return None

        # Return converted value
        return self(record[field_id])


class StringField(AdvancedCSVField):
    """
    Field is StringField by default
    """
    pass


class TimestampField(TimestampFieldMixin, AdvancedCSVField):
    """
    Field which converts string values to timestamps
    """
    pass


class IntegerField(IntegerFieldMixin, AdvancedCSVField):
    """
    Field which converts string values to integer
    """
    pass
