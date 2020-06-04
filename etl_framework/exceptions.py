class ETLError(Exception):
    """Base class for all custom Ingest errors"""
    pass

class FileAlreadyExistsError(ETLError):
    pass

class ETLConfigurationError(ETLError):
    pass

class UnsupportedOperatorError(ETLError):
    """
    WHen operation is used with unsupported operand
    """
    pass

class EndOfFileError(ETLError):
    """Raised when end of file has been reached"""
    pass

class MissingFieldError(ETLError):
    """Error for when an expected field is missing"""
    pass


class ValidationError(ETLError):
    """Exception class used to indicate a field value validation has failed"""
    pass

class RecordSkipError(ETLError):
    """Exception class for when validation fails and record should be skipped"""
    pass

class FieldDQError(ETLError):
    """Exception class for when validation fails and error should be raised"""
    pass

class ETLRecordError(ETLError):
    """Base exception for record-level errors"""
    pass

class ConverterConfigurationError(ETLError):
    pass

class RecordLengthError(ETLRecordError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class RecordMatchError(ETLRecordError):
    """When field data format is not as expected, or missing when mandatory"""
    pass





class ASNDecodeError(ETLError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class ETLFieldError(ETLError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class FieldValidationError(ETLFieldError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class FieldMatchError(FieldValidationError):
    """When field data format is not as expected, or missing when mandatory"""
    pass


class FieldOptionError(FieldValidationError):
    """When a mandatory field is missing"""
    pass


class FieldFormatError(FieldValidationError):
    """When a lookup field contains a value not in lookup table"""
    pass


class FieldLengthError(FieldValidationError):
    """When a lookup field contains a value not in lookup table"""
    pass


class FieldMandatoryError(FieldValidationError):
    """When a mandatory field is missing"""
    pass


class FieldLookupError(ETLFieldError):
    """When a lookup field contains a value not in lookup table"""
    pass





class FieldTransformError(ETLFieldError):
    """Error during transformation of field"""
    pass


class MissingLookupError(FieldTransformError):
    """Error during transformation of field"""
    pass