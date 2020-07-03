
cpdef (bint, unsigned long long, unsigned long long, unsigned long long) decode_tag(bytes asn_data, unsigned long long start_pos, unsigned long long parent_id):
        """
        Decode the ASN1 node starting at specified start_pos in the ASN1 data file.
        """
        cdef unsigned char tag_len, tag_number, byte, len_byte, num_length_bytes
        cdef unsigned int value_len
        cdef bint constructed
        cdef unsigned long long end_pos, id
        cdef bint indefinite

        indefinite = False
        byte = asn_data[start_pos]
        # ----------GET TAG CLASS AND TYPE----------------#
        # Get tag class (0 - Universal, 1- Application, 2 - Context-Specific, 3- Private)
        # tag_class = asn_data[start_pos] & 0xc0
        # Get tag type (0 - Primitive, 1 - Constructed)
        constructed = byte & 0x20
        # ----------GET TAG NUMBER---------------------#
        tag_number = byte & 0x1f
        # Tag length keeps track of how many bytes haved been used while decoding tag data (can vary in case of long tag number or long length)
        tag_len = 1
        # Case of long tag number (actual number is encoded in following octets)
        if tag_number == 0x1f:
            # Initialise tag number
            tag_number=0
            while True:
                byte = asn_data[start_pos + tag_len]
                tag_number = (tag_number<<7) + (byte & 0x7f)
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
                value_len=0
                for byte in asn_data[start_pos + tag_len: start_pos + tag_len + num_length_bytes]:
                    value_len = (value_len<<8) + byte
                tag_len+=num_length_bytes
            else:  # Indefinite length field
                value_len = 0
                indefinite = True
        else:
            # Standard length
            value_len = len_byte & 0x7f
        # Calculate absolute ID of node
        id = (tag_number if parent_id==0 else (parent_id<<8) + tag_number) + 1
        # Calculate end position
        end_pos = 0 if indefinite else (start_pos + tag_len + value_len)

        return  (constructed, id, start_pos + tag_len, end_pos)