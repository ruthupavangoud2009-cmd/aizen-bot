from discord.ext import commands


class KyokaException(commands.CommandError):
    """Base exception class for Kyoka Bot."""
    pass


class NotAuthorizedError(KyokaException):
    """Raised when user lacks high-level permission."""
    pass


class DatabaseError(KyokaException):
    """Raised when database query fails."""
    pass
