from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """Profil utilisateur étendu (devise, langue, pays)."""

    LANG_CHOICES = [("fr", "Français"), ("en", "English")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone_number = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, blank=True)
    default_currency = models.CharField(max_length=3, default="XOF")
    language = models.CharField(max_length=2, choices=LANG_CHOICES, default="fr")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_user_profile"

    def __str__(self):
        return f"Profile of {self.user.email}"


class PasswordResetOTP(models.Model):
    """OTP pour réinitialisation du mot de passe (valide 15 min)."""

    email = models.EmailField(db_index=True)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "accounts_password_reset_otp"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.email} (expires {self.expires_at})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
