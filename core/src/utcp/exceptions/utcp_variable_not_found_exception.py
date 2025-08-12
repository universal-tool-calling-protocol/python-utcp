class UtcpVariableNotFound(Exception):
    """Exception raised when a required variable cannot be found.

    This exception is thrown during variable substitution when a referenced
    variable cannot be resolved through any of the configured variable sources.
    It provides information about which variable was missing to help with
    debugging configuration issues.

    Attributes:
        variable_name: The name of the variable that could not be found.
    """
    variable_name: str

    def __init__(self, variable_name: str):
        """Initialize the exception with the missing variable name.

        Args:
            variable_name: Name of the variable that could not be found.
        """
        self.variable_name = variable_name
        super().__init__(f"Variable {variable_name} referenced in provider configuration not found. Please add it to the environment variables or to your UTCP configuration.")
