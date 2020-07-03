import pyximport; pyximport.install(language_level="3", inplace=True)
from .asn1_decoder import ASN1BERDecoder
from etl_framework.operations.pandas.record_extractors.files import decode_tag

class ASN1CythonDecoder(ASN1BERDecoder):
    """
    ASN1 decoder class which uses cython function to decode tag details for better performance
    """

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

        # Decode ASN1 node details
        constructed, id, value_pos, end_pos = decode_tag(self.asn_data, start_pos, parent_node['id'] if parent_node else 0)
        # --------------CONSTRUCT NODE------------------#
        node = {
            'constructed': constructed,
            'id': id,
            'start_pos': start_pos,
            'value_pos': value_pos,
            'end_pos': end_pos,
            'parent': parent_node
        }
        return node