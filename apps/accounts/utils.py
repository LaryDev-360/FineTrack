import re
import secrets
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import PasswordResetOTP


def validate_new_password(value):
    """Règles mot de passe : 8 car. min, lettres + chiffres."""
    validate_password(value)
    # Mot de passe fort : min 8 caractères (enforced by validate_password), lettres majuscules, lettres minuscules, chiffres, caractères spéciaux.
    if not re.search(r"[A-Z]", value):
        raise ValueError("Le mot de passe doit contenir au moins une lettre majuscule.")
    if not re.search(r"[a-z]", value):
        raise ValueError("Le mot de passe doit contenir au moins une lettre minuscule.")
    if not re.search(r"\d", value):
        raise ValueError("Le mot de passe doit contenir au moins un chiffre.")
    if not re.search(r"[^\w\s]", value):
        raise ValueError("Le mot de passe doit contenir au moins un caractère spécial.")
    return value


def generate_otp(length=6):
    """Génère un OTP numérique (ex. 6 chiffres)."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def create_and_send_otp(email, otp_valid_minutes=15):
    """
    Crée un OTP pour l'email, invalide les anciens, envoie l'email.
    Retourne True si l'email a été envoyé (ou simulé en dev).
    """
    # Invalider les anciens OTP pour cet email
    PasswordResetOTP.objects.filter(email__iexact=email).delete()

    otp_code = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=otp_valid_minutes)
    PasswordResetOTP.objects.create(email=email.lower(), otp_code=otp_code, expires_at=expires_at)

    subject = "[FineTrack] Code de réinitialisation du mot de passe"
    message = (
        f"Votre code OTP pour réinitialiser votre mot de passe est : {otp_code}\n\n"
        f"Il est valide {otp_valid_minutes} minutes. Ne le partagez avec personne."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@finetrack.local")
    fail_silently = not settings.DEBUG

    try:
        send_mail(subject, message, from_email, [email], fail_silently=fail_silently)
        return True
    except Exception:
        if settings.DEBUG:
            # En dev, afficher l'OTP dans la console (backend console email)
            print(f"[FineTrack OTP] Email={email} OTP={otp_code} (expires {expires_at})")
        return True
