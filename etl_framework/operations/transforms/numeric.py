from etl_framework.operations import Operation


class IntToHexString(Operation):
    """
    Convert integer to BCD hex string
    Effectively gets binary representation of integer and breaks it into 4-bit blocks
    e.g. 361696856919591232 -> '505016001114940'
    """
    def __init__(self, hex_length=None):
        """

        :param int hex_length: Expected length of output hex string. If specified and output is shorter, will be zero-padded as required
        """
        super().__init__()
        self.hex_length = hex_length

    def action(self, value):
        # Trim off '0x' from start of string
        hex_str = hex(value)[2:]
        # 0-pad hex string if required
        if self.hex_length and len(hex_str) < self.hex_length:
            hex_str = hex_str.zfill(self.hex_length)

        return hex_str