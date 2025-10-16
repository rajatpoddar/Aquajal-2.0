# File: generate_keys.py
# A simple, reliable script to generate VAPID keys.

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

def generate_vapid_keys():
    """
    Generates a private and public VAPID key pair.
    """
    # Generate a private key using the SECP256R1 curve (also known as P-256)
    private_key = ec.generate_private_key(ec.SECP256R1())

    # Get the public key in uncompressed format
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    # VAPID keys are URL-safe base64 encoded and without padding
    private_key_b64 = base64.urlsafe_b64encode(
        private_key.private_numbers().private_value.to_bytes(32, 'big')
    ).rstrip(b'=').decode('utf-8')

    public_key_b64 = base64.urlsafe_b64encode(
        public_key
    ).rstrip(b'=').decode('utf-8')

    return private_key_b64, public_key_b64

if __name__ == '__main__':
    private, public = generate_vapid_keys()
    print("VAPID Keys Generated Successfully!")
    print("=================================")
    print(f"Public Key:  {public}")
    print(f"Private Key: {private}")
    print("=================================")
    print("\nCopy these keys into your .env file.")
