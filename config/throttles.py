"""Throttling par scope pour les endpoints d’authentification (limitation par IP)."""

from rest_framework.throttling import SimpleRateThrottle


class RegisterThrottle(SimpleRateThrottle):
    scope = "register"


class LoginThrottle(SimpleRateThrottle):
    scope = "login"


class PasswordResetThrottle(SimpleRateThrottle):
    scope = "password_reset"


class TokenRefreshThrottle(SimpleRateThrottle):
    scope = "refresh"
