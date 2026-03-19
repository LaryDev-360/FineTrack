from django.urls import path

from .views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    RefreshView,
    RegisterView,
    VerifyOTPView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
    # Forget password (OTP by email)
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/verify/", VerifyOTPView.as_view(), name="password-reset-verify"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    # Change password (authenticated)
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
]
