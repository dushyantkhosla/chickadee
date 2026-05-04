class FetchError(Exception):
    """Raised when content cannot be fetched from a URL."""


class ParseError(Exception):
    """Raised when fetched content cannot be parsed or extracted."""


class VaultWriteError(Exception):
    """Raised when a note cannot be written to the vault."""
