class UtcpSerializerValidationError(Exception):
    """REQUIRED
    Exception raised when a serializer validation fails.

    Thrown by serializers when they cannot validate or convert data structures
    due to invalid format, missing required fields, or type mismatches.
    Contains the original validation error details for debugging.

    Usage:
        Typically caught when loading configuration files or processing
        external data that doesn't conform to UTCP specifications.
    """
