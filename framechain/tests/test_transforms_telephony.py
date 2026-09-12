from unittest import TestCase

from framechain.operations.transforms.telephony import IPv6AddressStringToBinary


class TelephonyTransformsTests(TestCase):

    def test_ipv6_str_to_bytes(self):
        test_data = [
            ('2001:0db8:0001:0000:0000:0ab9:C0A8:0102',
             b'\x20\x01\x0d\xb8\x00\x01\x00\x00\x00\x00\x0a\xb9\xc0\xa8\x01\x02'),
            # With no padded zeros
            ('2001:8004:e002:3:179c:95c8:d392:531d',
             b'\x20\x01\x80\x04\xe0\x02\x00\x03\x17\x9c\x95\xc8\xd3\x92\x53\x1d')
        ]
        transform = IPv6AddressStringToBinary()
        for input_val, output_val in test_data:
            self.assertEqual(transform(input_val), output_val)