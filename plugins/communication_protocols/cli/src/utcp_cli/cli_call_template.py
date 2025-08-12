
class CliProvider(CallTemplate):
    """Provider configuration for Command Line Interface tools.

    Enables execution of command-line tools and programs as UTCP providers.
    Supports environment variable injection and custom working directories.

    Attributes:
        type: Always "cli" for CLI providers.
        command_name: The name or path of the command to execute.
        env_vars: Optional environment variables to set during command execution.
        working_dir: Optional custom working directory for command execution.
        auth: Always None - CLI providers don't support authentication.
    """

    type: Literal["cli"] = "cli"
    command_name: str
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables to set when executing the command")
    working_dir: Optional[str] = Field(default=None, description="Working directory for command execution")
    auth: None = None