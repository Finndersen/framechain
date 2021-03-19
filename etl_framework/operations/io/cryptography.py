from etl_framework.operations.base import Operation
import os, io


class DecryptDataAESGCM(Operation):
    """
    Decrypt AES GCM encrypted binary data
    Input data consists of:
    salt (32 bits) + nonce (16 bits) + ciphertext + auth tag (16 bits)
    """
    BUFFER_SIZE = 1024 * 1024  # The size in bytes that we read, encrypt and write to at once

    def __init__(self, password):
        """

        :param str password: Text password used to decrypt data
        """
        self.password = password

    def action(self, encrypted_data):
        """

        :param bytes encrypted_data: Encrypted data including salt, nonce, ciphertext and auth tag
        :return:
        """
        # Import here so only needed when operation is used
        from Crypto.Cipher import AES
        from Crypto.Protocol.KDF import scrypt
        salt = encrypted_data[:32]
        nonce = encrypted_data[32:48]
        ciphertext = io.BytesIO(encrypted_data[48:-16])
        auth_tag = encrypted_data[-16:]

        # Get key from salt and password
        key = scrypt(self.password, salt, key_len=32, N=2 ** 17, r=8, p=1)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

        # Verify tag (raises ValueError if fails)
        cipher.verify(auth_tag)

        encrypted_data_size = len(encrypted_data) - (32 + 16 + 16)

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








