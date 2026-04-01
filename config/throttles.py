"""Throttling par scope pour les endpoints d’authentification (limitation par IP)."""

from rest_framework.throttling import AnonRateThrottle


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class TokenRefreshThrottle(AnonRateThrottle):
    scope = "refresh"
