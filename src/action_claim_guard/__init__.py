"""Action Claim Guard: receipt-grounded claim checks for local AI agents."""
from .api import check_reply
from .engine import validate_response_claims
__all__ = ["check_reply", "validate_response_claims"]
__version__ = "0.1.0"
