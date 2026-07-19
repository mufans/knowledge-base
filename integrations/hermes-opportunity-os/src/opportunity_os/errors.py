class OpportunityOSError(Exception):
    """Base error for the opportunity discovery system."""


class ValidationError(OpportunityOSError, ValueError):
    """Raised when an object violates a deterministic invariant."""


class BoundaryError(OpportunityOSError, PermissionError):
    """Raised when a path crosses the public/private boundary."""


class CapacityError(ValidationError):
    """Raised when a direction portfolio exceeds its capacity."""
