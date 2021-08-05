from etl_framework import exceptions
from collections import defaultdict
import logging

log = logging.getLogger(__name__)


class SkipRecordError(Exception):
    """
    Exception for skipping entire root-level ASN1 record
    """
    pass


class ASN1Node(object):
    """
    Object to represent ASN1 node
    """
    __slots__ = ('constructed', 'tag_number', 'id', 'start_pos', 'value_pos', 'end_pos', 'parent', 'depth')

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
        self.depth = parent.depth + 1 if parent else 0
        # Calculate unique absolute ID of node (add 1 so it will always contribute something)
        self.id = (tag_number if parent is None else (parent.id<<8) + tag_number) + 1


class ASN1BERDecoder(object):
    RECORDTYPE_FIELD_NAME = '_record_type'
    RECORDNUMBER_FIELD_NAME = '_record_number'

    def __init__(self, record_types, fields, data_skipper=None):
        """
        Initialise ASN1 Decoder class with configuration

        :param list record_types: List of ASN1RecordType instances representing recordtypes of interest
        :param list fields: List of ASN1BERField or subclasses, representing fields to be extracted
        :param data_skipper: Function used to skip header/trailer/filler data before an ASN1 record. Takes record data and current index, returns new index
        """
        record_type_names = {record_type.name for record_type in record_types}
        field_names = set()
        for field in fields:
            # Validate all field mappings use defined recordtype
            if isinstance(field.asn_ids, dict):
                for record_type_name in field.asn_ids:
                    if record_type_name not in record_type_names:
                        raise exceptions.ETLConfigurationError('Record Type {} defined in {} configuration is invalid'.format(record_type_name, field))

            # Validate no duplicate field names
            if field.name in field_names:
                raise ValueError('Field with name: "{}" has already been defined'.format(field.name))

            # Validate no field has same name as recordtype field name
            if field.name == self.RECORDTYPE_FIELD_NAME:
                raise exceptions.ETLConfigurationError('ASN1 record schema defined with field name same as recordtype field name: {}'.format(
                               self.RECORDTYPE_FIELD_NAME))

            # Validate no field has same name as recordtype field name
            if field.name == self.RECORDNUMBER_FIELD_NAME:
                raise exceptions.ETLConfigurationError('ASN1 record schema defined with field name same as recordtype number name: {}'.format(
                               self.RECORDNUMBER_FIELD_NAME))

            field_names.add(field.name)

        self.asn_data = self.record_node = None
        self.asn_index = self.record_number = 0
        self.data_skipper = data_skipper
        # Validate record types have same ASN ID depth
        assert all([record_type.id_depth == record_types[0].id_depth for record_type in
                    record_types]), "All record schemas must have same recordtype tag length"

        self.recordtype_depth = record_types[0].id_depth
        self.target_recordtypes = {convert_asn_tag_to_unique_integer(record_type.asn_id): record_type
                                   for record_type in record_types}

        # Construct mapping of field unique ASN ID to list of field instances, for all target fields
        # (across all record types - different record type will automatically have different field ASN ID)
        self.target_fields = defaultdict(list)
        for record_type in record_types:
            for field in fields:
                if field.applicable_to_record_type(record_type):
                    field_absolute_id = convert_asn_tag_to_unique_integer(field.get_asn_id_for_record_type(record_type))
                    self.target_fields[field_absolute_id].append(field)

    def set_asn_data(self, asn_data):
        """
        Load file to be decoded

        :param asn_data: Binary data of ASN1 file
        :return:
        """
        self.asn_data = asn_data
        self.asn_index = 0
        self.record_node = None
        self.record_number = 0

    def skip_until_asn_block(self):
        """
        Skips through file content (e.g. blanks, newlines, headers/trailers) until reach start of ASN1 node data.
        :return:
        """
        # while 1:
        try:
            # new_index = self.asn_index
            if self.data_skipper:
                self.asn_index = self.data_skipper(self.asn_data, self.asn_index)

            # if new_index == self.asn_index:
            #     # Nothing skipped, should be start of record
            #     break
            # elif new_index > self.asn_index:
            #     self.asn_index = new_index
            # else:
            #     raise ValueError('New data index: {} should be greater than previous: {}'.format(new_index,
            #                                                                                      self.asn_index))
        except IndexError:
            raise exceptions.EndOfFileError()

    def decode_node(self, parent_node, start_pos=None):
        """
        Decode the ASN1 node starting at specified start_pos in the ASN1 data file.
        If no start_pos is specified, current asn_index is used
        :param ASN1Node parent_node: Parent ASN1 node
        :param int start_pos: Start position of ASN1 node in data file
        :return: ASN1Node: Decoded ASN1Node object
        """

        if start_pos is None:
            start_pos = self.asn_index

        # ----------GET TAG CLASS AND TYPE----------------#
        # Get tag class (0 - Universal, 1- Application, 2 - Context-Specific, 3- Private)
        # tag_class = self.asn_data[start_pos] & 0xc0
        # Get tag type (0 - Primitive, 1 - Constructed)
        constructed = bool(self.asn_data[start_pos] & 0x20)
        # ----------GET TAG NUMBER---------------------#
        tag_number = self.asn_data[start_pos] & 0x1f
        # Tag length keeps track of how many bytes haved been used while decoding tag data (can vary in case of long tag number or long length)
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
                for byte in self.asn_data[start_pos + tag_len: start_pos + tag_len + num_length_bytes]:
                    value_len = (value_len << 8) + byte
                tag_len += num_length_bytes
            else:  # Indefinite length field
                value_len = None
        else:
            # Standard length
            value_len = len_byte & 0x7f

        return ASN1Node(tag_number, constructed, start_pos, tag_len, value_len, parent_node)

    def build_asn_record(self, record_node=None):
        """
        Entry point for constructing record dictionary from provided root node (corresponds to full ASN1 record)
        Creates record in form of dictionary of field names and values
        Returns None if record is skipped (not target record type)
        :param ASN1Node record_node: Root-level ASN1 node of record to decode
        (get automatically from current data position if not specified)
        :return:
        """
        self.record_node = record_node or self.decode_node(None)
        self.record_number += 1
        record_data = {self.RECORDNUMBER_FIELD_NAME: self.record_number}
        try:
            self.traverse_asn(self.record_node, record_data=record_data)
        except SkipRecordError:
            return None

        return record_data

    def traverse_asn(self, node, record_data=None):
        """
        Traverse through an ASN1 node including all its children (if it is a constructed node)
        If current_record dictionary is supplied, it will look for fields defined in target_record_schema
        and populate current_record dictionary with the field value and field id as key
        :param ASN1Node node:
        :param dict record_data:
        :return:
        """
        # If record is being built, detect recordtype or add node value
        if record_data is not None:

            if node.depth == self.recordtype_depth:
                if node.id in self.target_recordtypes:
                    # Set record type field
                    record_data[self.RECORDTYPE_FIELD_NAME] = self.target_recordtypes[node.id].name
                else:  # Skip irrelevant record type
                    self.skip_node(self.record_node)
                    raise SkipRecordError()

            # Add field data to record if ID is a target field
            elif (not node.constructed) and (node.id in self.target_fields):
                raw_field_value = self.get_node_value(node)
                # Can be multiple field extractions for single ASN1 field
                fields = self.target_fields[node.id]
                for field in fields:
                    field.add_to_record(record_data, raw_field_value)

        # Traverse through children of constructed node
        if node.constructed:
            self.asn_index = node.value_pos
            while True:
                child_node = self.decode_node(node)
                self.traverse_asn(child_node, record_data=record_data)
                if self.is_node_last_child(child_node):
                    # Update end position if node is indefinite length
                    if node.end_pos is None:
                        node.end_pos = child_node.end_pos + 2
                    break

        # Update current ASN index.
        self.asn_index = node.end_pos

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
            raise exceptions.ASNDecodeError('Cannot get data of node with no end position')

    def skip_node(self, node):
        """
        Update asn_index to end of current node
        If Node is definite (length known) then this is trivial.
        For indefinite length nodes, must traverse ASN structure
        :param ASN1Node node:
        :return:
        """
        # print('Skipping node: {}'.format(node))
        # Set ASN index to node end pos if node has definite length
        if node.end_pos is not None:
            self.asn_index = node.end_pos
        else:
            # Traverse through indefinite length constructed node to get next node
            self.traverse_asn(node)

    def next_node(self, node):
        """
        Skip ASN1 index to end of current node and decode next node
        :param ASN1Node node:
        :return:
        """
        self.skip_node(node)
        return self.decode_node(node.parent)

    def first_child_node(self, node):
        """
        Get first child node of parent constructed node
        :param ASN1Node node:
        :return:
        """
        if node.constructed:
            return self.decode_node(node, node.value_pos)
        else:
            raise exceptions.ASNDecodeError('Cant get child node of primitive node')


def convert_asn_tag_to_unique_integer(asn_tag):
    """
    Converts ASN tag in string form to unique integer which is more efficient for comparison and calculation
    Assume maximum tag ID value is 255, meaning each successive tag depth gets bit shifted by 8 places then added
    :param str asn_tag: ASN tag as string containing hyphen-seperated integers e.g. '0-1-4'
    :return:
    """
    return sum((int(asn_id) + 1) << (8 * i) for i, asn_id in enumerate(reversed(asn_tag.split('-'))))


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
