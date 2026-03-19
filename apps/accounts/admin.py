from django.contrib import admin
from .models import PasswordResetOTP, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "default_currency", "language", "country")


@admin.register(PasswordResetOTP)
class PasswordResetOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "otp_code", "created_at", "expires_at")
    list_filter = ("email",)
