class TextProvider(CallTemplate):
    """Provider configuration for text file-based tools.

    Reads tool definitions from local text files, useful for static tool
    configurations or when tools generate output files at known locations.

    Use Cases:
        - Static tool definitions from configuration files
        - Tools that write results to predictable file locations
        - Download manuals from a remote server to allow inspection of tools
            before calling them and guarantee security for high-risk environments

    Attributes:
        type: Always "text" for text file providers.
        file_path: Path to the file containing tool definitions.
        auth: Always None - text providers don't support authentication.
    """

    type: Literal["text"] = "text"
    file_path: str = Field(..., description="The path to the file containing the tool definitions.")
    auth: None = None
