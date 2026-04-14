class SlotUnavailableError(Exception):
    """Raised when the requested slot is no longer available."""


class BookingNotFoundError(Exception):
    """Raised when the appointment does not exist."""
