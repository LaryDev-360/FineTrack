import re
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import UserProfile
from .utils import validate_new_password

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login par email + mot de passe ; retourne access + refresh tokens."""

    username_field = User.EMAIL_FIELD  # "email"

    def validate(self, attrs):
        email = attrs.get(self.username_field) or ""
        password = attrs.get("password") or ""
        email = email.lower().strip() if isinstance(email, str) else ""

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = None

        # Message volontairement identique au SimpleJWT (FR/EN selon configuration).
        if not user or not user.is_active:
            raise AuthenticationFailed("Aucun compte actif n'a été trouvé avec les identifiants fournis")
        if not user.check_password(password):
            raise AuthenticationFailed("Aucun compte actif n'a été trouvé avec les identifiants fournis")

        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        return token


class RegisterSerializer(serializers.ModelSerializer):
    """Inscription : email + mot de passe (8 car. min, lettres + chiffres)."""

    email = serializers.EmailField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True, min_length=8, style={"input_type": "password"})
    password_confirm = serializers.CharField(required=True, write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("email", "password", "password_confirm")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value.lower()

    def validate_password(self, value):
        validate_password(value)
        if not re.search(r"[a-zA-Z]", value) or not re.search(r"\d", value):
            raise serializers.ValidationError("Le mot de passe doit contenir des lettres et des chiffres.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Les mots de passe ne correspondent pas."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        # Django User requires username; we use email as username
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=password,
        )
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ("phone_number", "country", "default_currency", "language")


class ProfileSerializer(serializers.ModelSerializer):
    """Profil complet : User (email, first_name) + UserProfile."""

    profile = UserProfileSerializer(required=False)

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "profile")
        read_only_fields = ("id", "email")

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if profile_data and hasattr(instance, "profile"):
            for attr, value in profile_data.items():
                setattr(instance.profile, attr, value)
            instance.profile.save()
        return instance


# --- Password reset (forget password) & change password ---


class PasswordResetRequestSerializer(serializers.Serializer):
    """Demande de réinitialisation : envoi d'un OTP par email."""

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.lower().strip()


class VerifyOTPSerializer(serializers.Serializer):
    """Vérification d'un code OTP (sans réinitialiser le mot de passe)."""

    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate_email(self, value):
        return value.lower().strip()

    def validate(self, attrs):
        from .models import PasswordResetOTP
        otp_record = (
            PasswordResetOTP.objects.filter(
                email__iexact=attrs["email"],
                otp_code=attrs["otp"],
            )
            .order_by("-created_at")
            .first()
        )
        if not otp_record:
            raise serializers.ValidationError({"otp": "Code OTP invalide."})
        if otp_record.is_expired:
            raise serializers.ValidationError({"otp": "Code OTP expiré. Demandez un nouveau code."})
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Confirmation avec OTP + nouveau mot de passe."""

    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, min_length=6, max_length=6)
    new_password = serializers.CharField(required=True, min_length=8, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(required=True, style={"input_type": "password"})

    def validate_email(self, value):
        return value.lower().strip()

    def validate_new_password(self, value):
        try:
            validate_new_password(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Les mots de passe ne correspondent pas."})

        from .models import PasswordResetOTP
        otp_record = (
            PasswordResetOTP.objects.filter(
                email__iexact=attrs["email"],
                otp_code=attrs["otp"],
            )
            .order_by("-created_at")
            .first()
        )
        if not otp_record:
            raise serializers.ValidationError({"otp": "Code OTP invalide ou expiré."})
        if otp_record.is_expired:
            otp_record.delete()
            raise serializers.ValidationError({"otp": "Code OTP expiré. Demandez un nouveau code."})

        attrs["_otp_record"] = otp_record
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    """Changement de mot de passe (utilisateur connecté)."""

    old_password = serializers.CharField(required=True, style={"input_type": "password"})
    new_password = serializers.CharField(required=True, min_length=8, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(required=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        try:
            validate_new_password(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
        return value

    def validate_old_password(self, value):
        user = self.context.get("request").user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Les mots de passe ne correspondent pas."})
        return attrs
