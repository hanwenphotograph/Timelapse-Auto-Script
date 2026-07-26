"""Application-specific exceptions."""


class TimelapseError(Exception):
    """Base exception shown to CLI and GUI users."""


class ConfigError(TimelapseError):
    """Configuration is missing or invalid."""


class TaskError(TimelapseError):
    """Task operation cannot be completed."""


class ProcessError(TimelapseError):
    """External process could not be managed."""
