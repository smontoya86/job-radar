"""Authentication module for Job Radar multi-user SaaS."""
from src.auth.exceptions import (
    AccountDisabledError,
    AuthenticationError,
    DuplicateEmailError,
    DuplicateUsernameError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidTokenError,
    WeakPasswordError,
)
from src.auth.service import AuthService, hash_password, verify_password

__all__ = [
    "AuthService",
    "hash_password",
    "verify_password",
    "AuthenticationError",
    "DuplicateEmailError",
    "DuplicateUsernameError",
    "WeakPasswordError",
    "InvalidEmailError",
    "InvalidCredentialsError",
    "AccountDisabledError",
    "InvalidTokenError",
]
