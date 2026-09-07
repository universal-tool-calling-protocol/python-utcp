class UtcpUnknownCallTemplateTypeError(Exception):
    """REQUIRED
    Exception raised when a call template names a type this client has no serializer for.

    Distinct from UtcpSerializerValidationError so that a manual loader can skip the
    one unloadable tool and keep the rest, instead of failing the whole manual.

    Attributes:
        call_template_type: The unregistered `call_template_type` value.
    """

    def __init__(self, call_template_type: str):
        self.call_template_type = call_template_type
        super().__init__(
            f"Unknown call template type: '{call_template_type}'. Install the plugin that"
            " registers it, or the tool will be skipped."
        )
