import os
import hashlib
import hmac
import base64
from typing import Tuple, Optional

# Check for cryptography library
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError:
    # MVP fallback or error if strict
    raise ImportError("The 'cryptography' library is required for secure pairing. Install with 'pip install cryptography'.")

def generate_otp() -> str:
    """Generate a 6-digit numeric OTP."""
    # Cryptographically secure random number
    random_bytes = os.urandom(4)
    val = int.from_bytes(random_bytes, "big")
    return f"{val % 1000000:06d}"

class PairingSession:
    """
    Implements a simplified secure pairing flow using X25519 and an OTP.
    
    Flow:
    1. Bob (Receiver) generates OTP and shows to user.
    2. Alice (Initiator) enters OTP.
    3. Alice & Bob exchange public keys.
    4. Both derive Shared Secret (ECDH).
    5. Both derive Session Key = HKDF(Shared Secret, salt=OTP).
    6. Both exchange confirmation MACs to verify they used the same OTP.
    """
    def __init__(self, role: str):
        self.role = role # 'initiator' or 'receiver'
        self._private_key = x25519.X25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._shared_key: Optional[bytes] = None
        self._session_key: Optional[bytes] = None

    def get_public_bytes(self) -> bytes:
        return self._public_key.public_bytes(
            encoding=x25519.Encoding.Raw,
            format=x25519.PublicFormat.Raw
        )

    def compute_shared_secret(self, peer_public_bytes: bytes, otp: str) -> None:
        peer_public_key = x25519.X25519PublicKey.from_public_bytes(
            peer_public_bytes
        )
        shared_secret = self._private_key.exchange(peer_public_key)
        
        # Mix OTP into the key derivation
        # Ideally PAKE logic uses OTP *before* exchange or blindly masks points,
        # but HKDF(ECDH, salt=OTP) ensures that if OTP is wrong, keys diverge.
        # This provides Forward Secrecy for the *session*, assuming OTP was safe for that moment.
        # Note: This is not a strong PAKE against active MITM who guesses OTP, 
        # but 6-digit OTP is short-lived.
        
        self._session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=otp.encode('utf-8'),
            info=b'silta-pairing-v1',
        ).derive(shared_secret)
        
        self._shared_key = shared_secret # Raw ECDH

    def get_confirmation_mac(self) -> bytes:
        """Return a MAC of 'role+public_key' keyed by session key to prove knowledge."""
        if not self._session_key: raise RuntimeError("Session key not established")
        
        h = hmac.new(self._session_key, digestmod=hashlib.sha256)
        h.update(self.role.encode('utf-8'))
        h.update(self.get_public_bytes())
        return h.digest()

    def verify_confirmation_mac(self, peer_mac: bytes, peer_role: str, peer_pub: bytes) -> bool:
        if not self._session_key: return False
        
        h = hmac.new(self._session_key, digestmod=hashlib.sha256)
        h.update(peer_role.encode('utf-8'))
        h.update(peer_pub)
        expected = h.digest()
        return hmac.compare_digest(expected, peer_mac)

    def get_session_key(self) -> bytes:
        if not self._session_key: raise RuntimeError("Session key not established")
        return self._session_key
