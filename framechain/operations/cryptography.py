from framechain.operations.base import Operation
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt
import os, io


class DecryptDataAES(Operation):
    """
    Decrypt AES GCM encrypted binary data
    Input data consists of:
    salt (32 bits) + nonce (16 bits) + ciphertext + auth tag (16 bits)
    """
    BUFFER_SIZE = 1024 * 1024  # The size in bytes that we read, encrypt and write to at once
    SALT_LEN = 32
    NONCE_LEN = 16
    AUTH_TAG_LEN = 16

    def __init__(self, password, mode, key_len=32):
        """

        :param str password: Text password used to decrypt data
        :param str mode: AES Decryption mode (ECB< CBC, CFB, GCM, OCB etc)
        """
        super().__init__()
        try:
            self.mode = getattr(AES, 'MODE_{}'.format(mode))
        except AttributeError:
            raise ValueError('"{}" is not a valid AES decryption mode'.format(mode))
        self.key_len = key_len
        self.password = password

    def action(self, encrypted_data):
        """

        :param bytes encrypted_data: Encrypted data including salt, nonce, ciphertext and auth tag
        :return:
        """
        salt = encrypted_data[:self.SALT_LEN]
        nonce = encrypted_data[self.SALT_LEN:self.SALT_LEN + self.NONCE_LEN]
        ciphertext = io.BytesIO(encrypted_data[self.SALT_LEN + self.NONCE_LEN:-self.AUTH_TAG_LEN])
        auth_tag = encrypted_data[-self.AUTH_TAG_LEN:]

        # Get key from salt and password
        key = scrypt(self.password, salt, key_len=self.key_len, N=2 ** 17, r=8, p=1)
        cipher = AES.new(key, self.mode, nonce=nonce)

        # Verify tag (raises ValueError if fails)
        # cipher.verify(auth_tag)

        encrypted_data_size = len(encrypted_data) - (self.SALT_LEN + self.NONCE_LEN + self.AUTH_TAG_LEN)

        output_data = io.BytesIO()
        # Decrypt data in chunks
        for _ in range(encrypted_data_size // self.BUFFER_SIZE):
            data = ciphertext.read(self.BUFFER_SIZE)  # Read in some data from the encrypted file
            output_data.write(cipher.decrypt(data))  # Decrypt the data
        # Decrypt remaining data
        data = ciphertext.read(encrypted_data_size % self.BUFFER_SIZE)  # Read in some data from the encrypted file
        output_data.write(cipher.decrypt(data))  # Decrypt the data
        
        output_data.seek(0)
        return output_data.read()








