from etl_framework import exceptions
import logging

log = logging.getLogger(__name__)


class ASN1BERDecoder(object):
    def __init__(self, record_types, fields, header_trailer_lengths):
        """
        Initialise ASN1 Decoder class with configuration

        :param list record_types: List of ASN1RecordType instances representing recordtypes of interest
        :param list fields: List of ASN1BERField or subclasses, representing fields to be extracted
        :param header_trailer_lengths: Mapping which describes format of the ASCII File and Logical header and trailer lines within the ASN1 file.
            Keys are binary representations of the first 2 bytes of the header/trailer line (e.g. b'\x46\x44' which corresponds to 'FD')
            Values are length of header/trailer line (how many positions to skip)
        """
        record_type_names = {record_type.name for record_type in record_types}
        for field in fields:
            # Validate all field mappings use defined recordtype
            if isinstance(field.asn_ids, dict):
                for record_type_name in field.asn_ids:
                    if record_type_name not in record_type_names:
                        raise exceptions.ETLConfigurationError('Record Type {} defined in {} configuration is invalid'.format(record_type_name, field))

        self.asn_data = self.current_record_type = None
        self.asn_index = self.current_depth = 0
        self.header_trailer_lengths = header_trailer_lengths or {}
        self.recordtype_depth = self.get_recordtype_depth(record_types)

        self.target_recordtypes = {convert_asn_tag_to_unique_integer(record_type.asn_id): record_type
                                   for record_type in record_types}

        # Construct mapping of field unique ASN ID to field instance, for all target fields (across all record types)
        self.target_fields = {}
        for record_type in record_types:
            for field in fields:
                if field.applicable_to_record_type(record_type):
                    field_absolute_id = convert_asn_tag_to_unique_integer(field.get_asn_id_for_record_type(record_type))
                    self.target_fields[field_absolute_id] = field

    def get_recordtype_depth(self, record_types):
        # Validate record types have same ASN ID depth
        assert all([record_type.id_depth == record_types[0].id_depth for record_type in
                    record_types]), "All record schemas must have same recordtype tag length"
        return record_types[0].id_depth

    def set_asn_data(self, asn_data):
        """
        Load file to be decoded

        :param asn_data: Binary data of ASN1 file
        :return:
        """
        self.asn_data = asn_data
        self.asn_index = 0
        self.current_record_type = None
        self.current_depth = 0

    def skip_until_asn_block(self):
        """
        Skips through file content until reach start of ASN1 node data.
        Skips through:
         - blanks/nulls (0)
         - newline characters (10)
         - ASCII headers and trailers as configured in header_trailer_lengths (e.g. FDAX2GSMCM10000273020150205102812)
        :return:
        """
        while 1:
            try:
                # Detect blanks
                if self.asn_data[self.asn_index] in {0, 10}:
                    self.asn_index += 1
                # Detect header/trailer (FD,LD,FT,LD)
                elif bytes(self.asn_data[self.asn_index:self.asn_index + 2]) in self.header_trailer_lengths:
                    # Skip header/trailer
                    header_len = self.header_trailer_lengths[bytes(self.asn_data[self.asn_index:self.asn_index + 2])]
                    self.asn_index += header_len
                else:
                    return
            except IndexError:
                raise exceptions.EndOfFileError()

    def decode_node(self, parent_node, start_pos=None):
        """
        Decode the ASN1 node starting at specified start_pos in the ASN1 data file.
        If no start_pos is specified, current asn_index is used
        :param dict parent_node: Parent ASN1 node
        :param int start_pos: Start position of ASN1 node in data file
        :return: dict: Dictionary representing ASN1 node details. Has attributes start_pos, value_pos, end_pos, type, parent, id
        """
        if start_pos is None:
            start_pos = self.asn_index

        indefinite = False

        # ----------GET TAG CLASS AND TYPE----------------#
        # Get tag class (0 - Universal, 1- Application, 2 - Context-Specific, 3- Private)
        # tag_class = self.asn_data[start_pos] & 0xc0
        # Get tag type (0 - Primitive, 1 - Constructed)
        constructed = self.asn_data[start_pos] & 0x20
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
                indefinite = True
        else:
            # Standard length
            value_len = len_byte & 0x7f

        # Calculate absolute ID of node
        id = (tag_number if parent_node is None else (parent_node['id']<<8) + tag_number) + 1
        # Calculate end position
        end_pos = 0 if indefinite else (start_pos + tag_len + value_len)
        # --------------CONSTRUCT NODE------------------#
        node = {
            'constructed': constructed,
            'id': id,
            'start_pos': start_pos,
            'value_pos': start_pos + tag_len,
            'end_pos': end_pos,
            'parent': parent_node
        }
        return node

    def build_asn_record(self, root_node):
        """
        Entry point for constructing record dictionary from provided root node (corresponds to full ASN1 record)
        Creates record in form of dictionary of field names and values
        :param root_node:
        :return:
        """
        record_data = {}
        self.current_record_type = None
        self.traverse_asn(root_node, record_data=record_data)
        return record_data

    def traverse_asn(self, node, record_data=None):
        """
        Traverse through an ASN1 node including all its children (if it is a constructed node)
        If current_record dictionary is supplied, it will look for fields defined in target_record_schema
        and populate current_record dictionary with the field value and field id as key
        :param dict node:
        :param dict record_data:
        :return:
        """
        # log.debug('Found ASN1 node: {} at Depth: {} '.format(node, self.current_depth))
        # If record is being built, detect recordtype or add node value
        if record_data is not None:
            # Skip irrelevant record type
            if self.current_depth == self.recordtype_depth:
                if node['id'] in self.target_recordtypes:
                    self.current_record_type = self.target_recordtypes[node['id']]
                else:
                    self.skip_node(node)
                    return

            # Add field data to record if ID is a target field
            elif (not node['constructed']) and (node['id'] in self.target_fields):
                field = self.target_fields[node['id']]
                field_value = field.convert_value(self.get_node_value(node))
                # Handle duplicate field entries (fields within SEQUENCE OF)
                if field.name in record_data:
                    record_data[field.name] = field.aggregate_values(record_data[field.name], field_value)
                else:
                    record_data[field.name] = field_value

        # Go through children of constructed node
        if node['constructed']:
            self.current_depth += 1
            self.traverse_asn(self.first_child_node(node), record_data=record_data)
            self.current_depth -= 1
        # Update current ASN index. If node is indefinite constructed, its end_pos will have been set by traversing children
        self.asn_index = node['end_pos']
        # If node has parent (non-root node), continue to next child or update parent length
        if node['parent']:
            # Continue to next node if not last child
            if not self.is_node_last_child(node):
                self.traverse_asn(self.next_node(node), record_data=record_data)
            # If node is last child and parent is indefinite length, update parent's length
            elif node['parent']['end_pos'] == 0:
                node['parent']['end_pos'] = node['end_pos'] + 2

    def is_node_last_child(self, node):
        """
        Check if node is last child of parent
        :param dict node:
        :return: bool
        """
        # If parent node is definite, can use length to determine if last child
        if node['parent']['end_pos'] != 0:
            return node['end_pos'] == node['parent']['end_pos']
        # Parent node is indefinite, check for 2 blanks to detect end of parent
        elif self.asn_data[node['end_pos']:node['end_pos'] + 2] == b'\x00\x00':
            return True
        else:
            return False

    def get_node_value(self, node):
        """
        Extract node data value from ASN data
        :param dict node:
        :return:
        """
        if node['end_pos'] != 0:
            return self.asn_data[node['value_pos']:node['end_pos']]
        else:
            raise exceptions.ASNDecodeError('Cannot get data of node with no end position')

    def skip_node(self, node):
        """
        Update asn_index to end of current node
        If Node is definite (length known) then this is trivial.
        For indefinite length nodes, must traverse ASN structure
        :param dict node:
        :return:
        """
        # Simple if node is primite or definite length constructed
        if node['end_pos'] != 0:
            self.asn_index = node['end_pos']
        else:
            # Traverse through indefinite length constructed node to get next node
            self.traverse_asn(node)

    def next_node(self, node):
        """
        Skip ASN1 index to end of current node and decode next node
        :param dict node:
        :return:
        """
        self.skip_node(node)
        return self.decode_node(node['parent'])

    def first_child_node(self, node):
        """
        Get first child node of parent constructed node
        :param dict node:
        :return:
        """
        if node['constructed']:
            return self.decode_node(node, node['value_pos'])
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