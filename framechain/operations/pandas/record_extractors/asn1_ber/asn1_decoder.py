import logging
from collections import defaultdict

from .exceptions import ASNDecodeError, EndOfFileError, OperationConfigurationError

log = logging.getLogger(__name__)


class PrettyDefaultDict(defaultdict):
    """
    Defaultdict which prints like a normal dict
    """
    __repr__ = dict.__repr__


# Create recursive/nested defaultdict
nested_defaultdict = lambda: PrettyDefaultDict(nested_defaultdict)


def get_nested_dict_key(dic, keys):
    """
    Get value in nested dict
    :param dict dic: Dictionary to set key in
    :param list keys:  Sequence of nested keys
    :param str key_delimiter:
    :return:
    """
    container = dic
    for key in keys:
        container = container[key]
    return container


def set_nested_dict_key(dic, keys, value, error_if_exists=False):
    """
    Set value in nested dict
    :param dict dic: Dictionary to set key in
    :param list keys:  Sequence of nested keys
    :param value: Value to set
    :param bool error_if_exists: Whether to raise error if key already exists
    :return:
    """
    # Get lowest-level container dict
    container = get_nested_dict_key(dic, keys[:-1])
    value_key = keys[-1]

    if error_if_exists and value_key in container:
        raise KeyError('Key "{}" already exists in dict: {}'.format(value_key, container))

    # Set value
    container[value_key] = value


class ASN1Node(object):
    """
    Object to represent ASN1 node
    """
    __slots__ = (
    'constructed', 'tag_number', 'id', 'start_pos', 'value_pos', 'end_pos', 'parent', 'depth')

    def __init__(self, tag_number, constructed, start_pos, tag_len, value_len, parent):
        """

        :param int tag_number: ASN tag number of node
        :param bool constructed: Whether node is constructed (True) or primitive (False)
        :param int start_pos: Start position of node in data
        :param int tag_len: Length of node tag data
        :param int value_len: Length of node value data (or None if indefinite field)
        :param ASN1Node parent: Parent node
        """
        self.tag_number = tag_number
        self.constructed = constructed
        self.start_pos = start_pos
        self.parent = parent

        self.value_pos = start_pos + tag_len
        self.end_pos = None if value_len is None else (start_pos + tag_len + value_len)

    def full_id(self):
        """
        Get Full ASN1 ID of node (hyphen-seperated tag number string format)
        :return:
        """
        if self.parent:
            return '{}-{}'.format(self.parent.full_id(), self.tag_number)
        else:
            return str(self.tag_number)

    def __repr__(self):
        return 'ASN1Node {} with data from {} to {} ({})'.format(self.full_id(),
                                                                 self.start_pos,
                                                                 self.end_pos if self.end_pos else '<Unknown>',
                                                                 'C' if self.constructed else 'P')


class ASN1BERDecoder(object):
    # Key used for record type name in target field structure
    RECORDTYPE_KEY = 'record_type'

    def __init__(self, record_types, fields, data_skipper=None,
                 record_type_field_name='_record_type'):
        """
        Initialise ASN1 Decoder class with configuration

        :param list record_types: List of ASN1RecordType instances representing recordtypes of interest
        :param list fields: List of ASN1BERField or subclasses, representing fields to be extracted
        :param data_skipper: Function used to skip header/trailer/filler data before an ASN1 record. Takes record data and current index, returns new index
        :param str record_type_field_name: Name of field to store record type name in
        """
        self.RECORDTYPE_FIELD_NAME = record_type_field_name
        record_type_names = {record_type.name for record_type in record_types}
        field_names = set()
        for field in fields:
            # Validate all field mappings use defined recordtype
            if isinstance(field.asn_ids, dict):
                for record_type_name in field.asn_ids:
                    if record_type_name not in record_type_names:
                        raise OperationConfigurationError(
                            'Record Type {} defined in {} configuration is invalid'.format(
                                record_type_name, field))

            # Validate no duplicate field names
            if field.name in field_names:
                raise ValueError(
                    'Field with name: "{}" has already been defined'.format(field.name))

            # Validate no field has same name as recordtype field name
            if field.name == self.RECORDTYPE_FIELD_NAME:
                raise OperationConfigurationError(
                    'ASN1 record schema defined with field name same as recordtype field name: {}'.format(
                        self.RECORDTYPE_FIELD_NAME))

            field_names.add(field.name)

        self.asn_data = self.data_len = None
        self.data_skipper = data_skipper

        # Build nested structure of target fields which matches ASN1 structure
        self.target_fields = nested_defaultdict()
        for record_type in record_types:
            for field in fields:
                if field.applicable_to_record_type(record_type):
                    field_absolute_id = field.get_asn_id_for_record_type(record_type)
                    set_nested_dict_key(self.target_fields,
                                        [int(tag_num) for tag_num in field_absolute_id.split('-')],
                                        field,
                                        error_if_exists=True)  # TODO: list of fields instead of just one
            # Add Record Type definitions to field structure
            set_nested_dict_key(self.target_fields,
                                [int(tag_num) for tag_num in record_type.asn_id.split('-')] + [
                                    self.RECORDTYPE_KEY],
                                record_type.name,
                                error_if_exists=True)

    def set_asn_data(self, asn_data):
        """
        Load file to be decoded

        :param asn_data: Binary data of ASN1 file
        :return:
        """
        self.asn_data = asn_data
        self.data_len = len(asn_data)

    def skip_until_asn_block(self, start_pos):
        """
        Skips through file content (e.g. blanks, newlines, headers/trailers) until reach start of ASN1 node data.
        :return: New index position after skipping data
        """
        try:
            if self.data_skipper:
                start_pos = self.data_skipper(self.asn_data, start_pos)

            if start_pos >= self.data_len:
                raise EndOfFileError()

            return start_pos

        except IndexError:
            raise EndOfFileError()

    def decode_node(self, start_pos, parent_node=None):
        """
        Decode the ASN1 node starting at specified start_pos in the ASN1 data file.
        If no start_pos is specified, current asn_index is used
        :param int start_pos: Start position of ASN1 node in data file
        :param ASN1Node parent_node: Parent ASN1 node
        :return: ASN1Node: Decoded ASN1Node object
        """
        # ----------GET TAG CLASS AND TYPE----------------#
        # Get tag class (0 - Universal, 1- Application, 2 - Context-Specific, 3- Private)
        # tag_class = self.asn_data[start_pos] & 0xc0
        # Get tag type (0 - Primitive, 1 - Constructed)
        constructed = bool(self.asn_data[start_pos] & 0x20)
        # ----------GET TAG NUMBER---------------------#
        tag_number = self.asn_data[start_pos] & 0x1f
        # Tag length keeps track of how many bytes haved been used while decoding tag data
        # (can vary in case of long tag number or long length)
        tag_len = 1
        # Case of long tag number (actual number is encoded in following octets)
        if tag_number == 0x1f:
            # Initialise tag number
            tag_number = 0
            while True:
                byte = self.asn_data[start_pos + tag_len]
                tag_number = (tag_number << 7) + (byte & 0x7f)
                tag_len += 1
                # If first bit of octet is set, means the tag number is continued in next octet
                if not byte & 0x80:
                    break
        # --------------GET VALUE LENGTH------------------#
        len_byte = self.asn_data[start_pos + tag_len]
        tag_len += 1
        # Handle case of long length or indefinite field
        if len_byte & 0x80:
            # Length actually encodes number of following length octets
            num_length_bytes = len_byte & 0x7f
            if num_length_bytes:  # Definite length field
                # calculate long value length
                value_len = 0
                len_start_pos = start_pos + tag_len
                for byte in self.asn_data[len_start_pos: len_start_pos + num_length_bytes]:
                    value_len = (value_len << 8) + byte
                tag_len += num_length_bytes
            else:  # Indefinite length field
                value_len = None
        else:
            # Standard length
            value_len = len_byte

        return ASN1Node(tag_number, constructed, start_pos, tag_len, value_len, parent_node)

    def decode_asn_record(self, start_pos):
        """
        Entry point for constructing record dictionary from provided root node (corresponds to full ASN1 record)
        Creates record in form of dictionary of field names and values
        Returns None if record is skipped (not target record type)
        (get automatically from current data position if not specified)
        :param int start_pos: Data position to decode ASN1 record from
        :return:
        """
        # Skip any headers or blank data
        start_pos = self.skip_until_asn_block(start_pos)
        record_data = {}
        root_node = self.decode_node(start_pos)
        self.extract_fields_from_node(root_node, self.target_fields, record_data)
        # If entire record is skipped, record data will be empty
        return record_data, root_node.end_pos

    def extract_fields_from_node(self, node, target_fields, record_data):
        """
        Traverse through an ASN1 node including all its children (if it is a constructed node)
        If current_record dictionary is supplied, it will look for fields defined in target_record_schema
        and populate current_record dictionary with the field value and field id as key
        :param ASN1Node node:
        :param dict target_fields: Dictionary of target fields for current container, with tag number keys
        :param dict record_data:
        :return:
        """
        if node.tag_number in target_fields:
            # Traverse through children of constructed node
            if node.constructed:
                node_target_fields = target_fields[node.tag_number]
                decode_pos = node.value_pos
                # Add Record Type
                if self.RECORDTYPE_KEY in node_target_fields:
                    record_data[self.RECORDTYPE_FIELD_NAME] = node_target_fields[
                        self.RECORDTYPE_KEY]
                # Extract fields from child nodes
                while True:
                    child_node = self.decode_node(decode_pos, parent_node=node)
                    # Traverse children of constructed child node
                    self.extract_fields_from_node(child_node, node_target_fields, record_data)
                    if self.is_node_last_child(child_node):
                        # Update end position if node is indefinite length
                        if node.end_pos is None:
                            node.end_pos = child_node.end_pos + 2
                        break
                    else:
                        decode_pos = child_node.end_pos
            else:
                # Add value of primitive node to record
                field = target_fields[node.tag_number]
                field.add_to_record(record_data, self.get_node_value(node))
                # TODO: Support multiple field extractions for single ASN1 field?

        # Skip indefinite length constructed node (set end_pos)
        elif node.end_pos is None:
            node.end_pos = self.get_indefinite_length_end_pos(node)

    def is_node_last_child(self, node):
        """
        Check if node is last child of parent
        :param ASN1Node node:
        :return: bool
        """
        # If parent node is definite, can use length to determine if last child
        if node.parent.end_pos is not None:
            return node.end_pos == node.parent.end_pos
        # Parent node is indefinite, check for 2 blanks to detect end of parent
        elif self.asn_data[node.end_pos:node.end_pos + 2] == b'\x00\x00':
            return True
        else:
            return False

    def get_node_value(self, node):
        """
        Extract node data value from ASN data
        :param ASN1Node node:
        :return:
        """
        if node.end_pos is not None:
            return self.asn_data[node.value_pos:node.end_pos]
        else:
            raise ASNDecodeError('Cannot get data of node with no end position')

    def get_indefinite_length_end_pos(self, node):
        """
        Traverse ASN structure of indefinite length node to find end_pos
        :param ASN1Node node:
        :return:
        """
        # Traverse through indefinite length constructed node to get next node
        decode_pos = node.value_pos
        while True:
            child_node = self.decode_node(decode_pos, parent_node=node)
            # Recursive skip indefinite child node
            if child_node.end_pos is None:
                child_node.end_pos = self.get_indefinite_length_end_pos(child_node)

            # If last child, update end position of node and current ASN index, adn exit loop
            if self.is_node_last_child(child_node):
                return child_node.end_pos + 2
            else:
                # Update ASN index to decode next node
                decode_pos = child_node.end_pos

    def first_child_node(self, node):
        """
        Get first child node of parent constructed node
        :param ASN1Node node:
        :return:
        """
        if node.constructed:
            return self.decode_node(node.value_pos, parent_node=node)
        else:
            raise ASNDecodeError('Cant get child node of primitive node')


def convert_asn_tag_to_unique_integer(asn_tag):
    """
    Converts ASN tag in string form to unique integer which is more efficient for comparison and calculation
    Assume maximum tag ID value is 255, meaning each successive tag depth gets bit shifted by 8 places then added
    :param str asn_tag: ASN tag as string containing hyphen-seperated integers e.g. '0-1-4'
    :return:
    """
    return sum(
        (int(asn_id) + 1) << (8 * i) for i, asn_id in enumerate(reversed(asn_tag.split('-'))))


class ASN1RecordType(object):
    """
    Simple object to define an ASN1 record type
    """

    def __init__(self, name, asn_id):
        """
        :param str name: name of record type
        :param str asn_id: constructed node ASN1 ID of record type (string of hyphen-seperated integers)
        """
        self.name = name
        self.asn_id = asn_id
        self.id_depth = len(asn_id.split('-')) - 1
