"""Authentication exceptions for Job Radar."""


class AuthenticationError(Exception):
    """Base exception for authentication errors."""

    pass


class DuplicateEmailError(AuthenticationError):
    """Raised when attempting to register with an email that already exists."""

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email already registered: {email}")


class DuplicateUsernameError(AuthenticationError):
    """Raised when attempting to register with a username that already exists."""

    def __init__(self, username: str):
        self.username = username
        super().__init__(f"Username already taken: {username}")


class WeakPasswordError(AuthenticationError):
    """Raised when password doesn't meet requirements."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Password too weak: {reason}")


class InvalidEmailError(AuthenticationError):
    """Raised when email format is invalid."""

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Invalid email format: {email}")


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are invalid."""

    def __init__(self):
        super().__init__("Invalid email or password")


class AccountDisabledError(AuthenticationError):
    """Raised when attempting to access a disabled account."""

    def __init__(self):
        super().__init__("Account is disabled")


class InvalidTokenError(AuthenticationError):
    """Raised when a password reset or verification token is invalid."""

    def __init__(self):
        super().__init__("Invalid or expired token")
