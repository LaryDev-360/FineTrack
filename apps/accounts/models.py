import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """Profil utilisateur étendu (type, devise, langue, pays)."""

    USER_TYPE_INDIVIDUAL = "individual"
    USER_TYPE_PROFESSIONAL = "professional"
    USER_TYPE_CHOICES = [
        (USER_TYPE_INDIVIDUAL, "Particulier"),
        (USER_TYPE_PROFESSIONAL, "Professionnel"),
    ]

    LANG_CHOICES = [("fr", "Français"), ("en", "English")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default=USER_TYPE_INDIVIDUAL,
        db_index=True,
    )
    phone_number = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, blank=True)
    default_currency = models.CharField(max_length=3, default="XOF")
    language = models.CharField(max_length=2, choices=LANG_CHOICES, default="fr")
    # Marchand (QR paiement) — uniquement pour user_type=professional
    merchant_id = models.UUIDField(unique=True, null=True, blank=True, editable=False, db_index=True)
    merchant_display_name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_user_profile"

    def ensure_merchant_id(self):
        """Génère un merchant_id unique si le profil est professionnel et n'en a pas."""
        if self.user_type == self.USER_TYPE_PROFESSIONAL and not self.merchant_id:
            self.merchant_id = uuid.uuid4()
            self.save(update_fields=["merchant_id"])

    def save(self, *args, **kwargs):
        if self.user_type == self.USER_TYPE_PROFESSIONAL and not self.merchant_id:
            self.merchant_id = uuid.uuid4()
        super().save(*args, **kwargs)

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
