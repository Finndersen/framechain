from etl_framework.operations.pandas.record_extractors.asn1_ber import ASN1BERDecoder
from numba import njit, uint64, uint8
from numba.core.types import UnicodeType


class ASN1Node(object):
    """
    Object to represent ASN1 node
    """
    __slots__ = ('constructed', 'tag_number', 'id', 'start_pos', 'value_pos', 'end_pos', 'parent', 'depth')

    def __init__(self, id,  tag_number, constructed, start_pos, value_pos, end_pos, depth, parent=None):
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
        self.value_pos = value_pos
        self.end_pos = end_pos
        self.depth = depth
        # Calculate unique absolute ID of node (add 1 so it will always contribute something)
        self.id = id

    def __repr__(self):
        return 'ASN1Node #{} from {} to {} ({})'.format(self.tag_number,
                                                        self.start_pos,
                                                        self.end_pos if self.end_pos else '<Unknown>',
                                                        'C' if self.constructed else 'P')

@njit
def decode_node(asn_data, start_pos, parent_id, parent_depth):
    """
    Decode the ASN1 node starting at specified start_pos in the ASN1 data file.
    If no start_pos is specified, current asn_index is used
    :param ASN1Node parent_node: Parent ASN1 node
    :param int start_pos: Start position of ASN1 node in data file
    :return: ASN1Node: Decoded ASN1Node object
    """
    # ----------GET TAG CLASS AND TYPE----------------#
    # Get tag class (0 - Universal, 1- Application, 2 - Context-Specific, 3- Private)
    # tag_class = self.asn_data[start_pos] & 0xc0
    # Get tag type (0 - Primitive, 1 - Constructed)
    constructed = bool(asn_data[start_pos] & 0x20)
    # ----------GET TAG NUMBER---------------------#
    tag_number = asn_data[start_pos] & 0x1f
    # Tag length keeps track of how many bytes haved been used while decoding tag data (can vary in case of long tag number or long length)
    tag_len = 1
    # Case of long tag number (actual number is encoded in following octets)
    if tag_number == 0x1f:
        # Initialise tag number
        tag_number = 0
        while True:
            byte = asn_data[start_pos + tag_len]
            tag_number = (tag_number << 7) + (byte & 0x7f)
            tag_len += 1
            # If first bit of octet is set, means the tag number is continued in next octet
            if not byte & 0x80:
                break
    # --------------GET VALUE LENGTH------------------#
    len_byte = asn_data[start_pos + tag_len]
    tag_len += 1
    # Handle case of long length or indefinite field
    if len_byte & 0x80:
        # Length actually encodes number of following length octets
        num_length_bytes = len_byte & 0x7f
        if num_length_bytes:  # Definite length field
            # calculate long value length
            value_len = 0
            for byte in asn_data[start_pos + tag_len: start_pos + tag_len + num_length_bytes]:
                value_len = (value_len << 8) + byte
            tag_len += num_length_bytes
        else:  # Indefinite length field
            value_len = None
    else:
        # Standard length
        value_len = len_byte & 0x7f

    value_pos = start_pos + tag_len
    end_pos = None if value_len is None else (start_pos + tag_len + value_len)
    depth =  0 if parent_depth is None else parent_depth + 1
    id = (tag_number if parent_id is None else (parent_id << 8) + tag_number) + 1

    return id, tag_number, constructed, start_pos, value_pos, end_pos, depth


class ASN1BEREncoderNumba(ASN1BERDecoder):
    
    def decode_node(self, parent_node=None, start_pos=None):
        if parent_node:
            return ASN1Node(*decode_node(self.asn_data,
                                         start_pos or self.asn_index,
                                         parent_node.id,
                                         parent_node.depth), parent_node)
        else:
            return ASN1Node(*decode_node(self.asn_data,
                                         start_pos or self.asn_index,
                                         None,
                                         None), None)