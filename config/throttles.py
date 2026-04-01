"""Throttling par scope pour auth et endpoints RAG."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class TokenRefreshThrottle(AnonRateThrottle):
    scope = "refresh"


class FundingQueryThrottle(UserRateThrottle):
    scope = "funding_query"


class FundingIngestThrottle(UserRateThrottle):
    scope = "funding_ingest"
