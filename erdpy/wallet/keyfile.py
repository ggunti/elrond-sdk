import base64
import sys

from binascii import hexlify, unhexlify, b2a_base64
from json import load
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


# References:
# Thanks for this implementation @flyingbasalt
# https://github.com/flyingbasalt/erdkeys
def load_from_key_file(key_file_json, password):
    with open(key_file_json) as json_f:
        keystore = load(json_f)

    backend = default_backend()

    # derive the decryption key
    kdf_name = keystore['crypto']['kdf']
    if kdf_name != 'scrypt':
        print('unknown key derivation function', kdf_name)
        sys.exit(1)

    salt = unhexlify(keystore['crypto']['kdfparams']['salt'])
    dklen = keystore['crypto']['kdfparams']['dklen']
    n = keystore['crypto']['kdfparams']['n']
    p = keystore['crypto']['kdfparams']['p']
    r = keystore['crypto']['kdfparams']['r']

    kdf = Scrypt(salt=salt, length=dklen, n=n, r=r, p=p, backend=backend)
    key = kdf.derive(bytes(password.encode()))

    # decrypt the private key with half of the decryption key
    cipher_name = keystore['crypto']['cipher']
    if cipher_name != 'aes-128-ctr':
        print('unknown cipher or mode', cipher_name)
        sys.exit(1)

    iv = unhexlify(keystore['crypto']['cipherparams']['iv'])
    ciphertext = unhexlify(keystore['crypto']['ciphertext'])
    decryption_key = key[0:16]

    cipher = Cipher(algorithms.AES(decryption_key), modes.CTR(iv), backend=backend)
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    pemified_private_key = b2a_base64(hexlify(plaintext))

    hmac_key = key[16:32]
    h = hmac.HMAC(hmac_key, hashes.SHA256(), backend=backend)
    h.update(ciphertext)
    mac = h.finalize()

    if mac != unhexlify(keystore['crypto']['mac']):
        print('invalid keystore (MAC does not match)')
        sys.exit(1)

    address_bech32 = keystore['bech32']
    private_key = ''.join([pemified_private_key[i:i + 64].decode() for i in range(0, len(pemified_private_key), 64)])

    key_hex = base64.b64decode(private_key).decode()
    key_bytes = bytes.fromhex(key_hex)

    seed = key_bytes[:32]

    return address_bech32, seed


def get_password(pass_file):
    with open(pass_file) as pass_f:
        return pass_f.read()
