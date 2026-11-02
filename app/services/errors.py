"""Errors raised while ingesting or transcribing a call."""


class ProviderConfigError(Exception):
    """The selected provider is missing a dependency or credential."""


class ProviderError(Exception):
    """The selected provider failed while handling a recording."""


class InvalidUploadError(Exception):
    """The upload cannot be stored."""


class UnsupportedMediaError(Exception):
    """The file extension is not a recording or a transcript."""


class DuplicateCallError(Exception):
    """This spool path was already ingested."""


class CallNotFoundError(Exception):
    """No stored call matches the requested id."""
