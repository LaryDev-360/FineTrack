import re
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
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

        # Ajout du claim `user_type` (particulier vs PME/professionnel)
        user_type = UserProfile.USER_TYPE_INDIVIDUAL
        if hasattr(user, "profile"):
            user_type = user.profile.user_type

        refresh = RefreshToken.for_user(user)
        refresh["user_type"] = user_type

        access = refresh.access_token
        access["user_type"] = user_type

        return {
            "refresh": str(refresh),
            "access": str(access),
        }

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        if hasattr(user, "profile"):
            token["user_type"] = user.profile.user_type
        else:
            token["user_type"] = UserProfile.USER_TYPE_INDIVIDUAL
        return token


class RegisterSerializer(serializers.ModelSerializer):
    """Inscription : email + mot de passe (+ type de compte optionnel)."""

    email = serializers.EmailField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True, min_length=8, style={"input_type": "password"})
    password_confirm = serializers.CharField(required=True, write_only=True, style={"input_type": "password"})
    user_type = serializers.ChoiceField(
        choices=UserProfile.USER_TYPE_CHOICES,
        default=UserProfile.USER_TYPE_INDIVIDUAL,
        required=False,
        write_only=True,
        help_text="individual (particulier) ou professional (professionnel). Par défaut : individual.",
    )

    class Meta:
        model = User
        fields = ("email", "password", "password_confirm", "user_type")

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
        user_type = validated_data.pop("user_type", UserProfile.USER_TYPE_INDIVIDUAL)
        password = validated_data.pop("password")
        try:
            user = User.objects.create_user(
                username=validated_data["email"],
                email=validated_data["email"],
                password=password,
            )
        except IntegrityError:
            raise serializers.ValidationError(
                {"email": "Un compte existe déjà avec cet email."}
            )
        if hasattr(user, "profile"):
            user.profile.user_type = user_type
            user.profile.save(update_fields=["user_type"])
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    user_type_display = serializers.CharField(source="get_user_type_display", read_only=True)
    merchant_id = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = (
            "user_type",
            "user_type_display",
            "merchant_id",
            "merchant_display_name",
            "phone_number",
            "country",
            "default_currency",
            "language",
        )

    def get_merchant_id(self, obj):
        return str(obj.merchant_id) if obj.merchant_id else None


class ProfileSerializer(serializers.ModelSerializer):
    """Profil complet : User (email, first_name) + UserProfile."""

    profile = UserProfileSerializer(required=False)

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "profile")
        read_only_fields = ("id", "email")

    def validate(self, attrs):
        """
        Évite les mises à jour accidentelles avec les données d'un autre utilisateur.
        Si `id` ou `email` sont fournis dans le payload, ils doivent correspondre
        exactement à l'utilisateur authentifié ciblé par /api/auth/profile/.
        """
        if not self.instance:
            return attrs

        errors = {}
        raw_id = self.initial_data.get("id", None)
        if raw_id is not None and str(raw_id) != str(self.instance.id):
            errors["id"] = "L'id fourni ne correspond pas à l'utilisateur connecté."

        raw_email = self.initial_data.get("email", None)
        if raw_email is not None and str(raw_email).strip().lower() != self.instance.email.lower():
            errors["email"] = "L'email fourni ne correspond pas à l'utilisateur connecté."

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

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
