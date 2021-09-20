

class SkipValues(object):
    """
    Used to skip certain byte values e.g. blanks, newlines
    """
    def __init__(self, values):
        if not all(isinstance(val, int) for val in values):
            raise ValueError('Provided values should be integers, not: {}'.format(values))
        self.values = set(values)

    def __call__(self, data, index):
        """
        Skip blank/null data and newlines
        :param data:
        :param index:
        :return:
        """
        while data[index] in self.values:
            index += 1

        return index


class SkipHeaders(object):
    """
    Used for skipping CMP and CHF (for CHF GPRS files) file and record headers data files.
    Also skips newline and  blank characters
    Can also handle case of no headers
    CHF GPRS Data is in format:
    •	CMP File Header
    •	CMP Logical Header
    •	CHF File Header (non-ASN.1 format)
    •	CHF CDR Header-1 (non-ASN.1 format)
    •	CDR-1 (ASN.1 format)
    •	………
    •	CHF CDR Header-n (non-ASN.1 format)
    •	CDR-n (ASN.1 format)
    •	Newline
    •	CMP Logical Trailer
    •	CMP Logical Header
    •	...
    •	Newline
    •	CMP Logical Trailer
    •	CMP File Trailer

    CHF File Header format:
    1-4: File Length
    5-8: Header Length
    ...

    CHF CDR Header Format (always 5 bytes long):
    1-2: CDR length
    ...
    """
    def __init__(self, chf_headers=False):
        # Whether current position is within CMP logical LD -> LT block
        self.in_cmp_block = False
        # Whether current positon is within CMP File FD -> FT
        self.in_cmp_file = False
        # End position for CHF 'file' within CMP logical block
        self.chf_file_end_pos = 0
        # Whether file contains CHF headers
        self.chf_headers = chf_headers

    def reset(self):
        """
        Reset state
        :return:
        """
        self.in_cmp_block = False
        self.in_cmp_file = False
        self.chf_file_end_pos = 0

    def __call__(self, data, index):
        """

        :param bytes data:
        :param int index:
        :return:
        """
        # Reset state for new file
        if index == 0:
            self.reset()

        while True:
            initial_index = index

            if not self.in_cmp_file and data[index:index+2] == b'\x46\x44':
                # print('{}: Skipping CMP File Header'.format(index))
                # SKip CMP File Header (FD)
                index += 34
                self.in_cmp_file = True

            # Detect CMP Logical Header (LD)
            if not self.in_cmp_block and data[index:index+2] == b'\x4c\x44':
                # print('{}: Skipping CMP Logical Header and CHF File header'.format(index))
                index += 41
                self.in_cmp_block = True

                if self.chf_headers:
                    # CHF File Header will be after CMP Logical Header
                    # Set position that CHF file ends
                    self.chf_file_end_pos = index + int.from_bytes(data[index:index+4], byteorder='big')
                    index += int.from_bytes(data[index + 4:index + 8], byteorder='big')

            # Skip CHF Record header
            if self.chf_headers and self.in_cmp_block and index < self.chf_file_end_pos:
                # print('{}: Skipping CHF record header'.format(index))
                index += 5
                # Will always be record after CHF Record header, can return
                return index

            # Detect CMP Logical Trailer (LT)
            if self.in_cmp_block and data[index:index+2] == b'\x4c\x54':
                # print('{}: Skipping CMP Logical Trailer'.format(index))
                self.in_cmp_block = False
                self.chf_file_end_pos = 0
                index += 49

            # Detect CMP FIle Trailer (FT)
            if not self.in_cmp_block and data[index:index+2] == b'\x46\x54':
                # print('{}: Skipping CMP File Trailer'.format(index))
                self.in_cmp_file = False
                index += 42
                # Should be end of file, can return
                return index

            # Skip newline or blank
            if data[index] in {0, 10}:
                # print('{}: Skipping Newline'.format(index))
                index += 1

            # Exit if no data skipped
            if index == initial_index:
                return index



