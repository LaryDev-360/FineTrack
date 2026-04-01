from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from config.throttles import (
    LoginThrottle,
    PasswordResetThrottle,
    RegisterThrottle,
    TokenRefreshThrottle,
)

from .models import UserProfile
from .serializers import (
    CustomTokenObtainPairSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    RegisterSerializer,
    VerifyOTPSerializer,
)
from .utils import create_and_send_otp


@extend_schema(
    tags=["Auth"],
    summary="Inscription",
    description="Crée un compte avec email et mot de passe (8 car. min, lettres + chiffres).",
    responses={201: {"description": "Compte créé. Connectez-vous via POST /api/auth/login/."}},
)
class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — Inscription (email + password)."""
    queryset = get_user_model().objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Create profile (signal does it, but ensure it exists)
        UserProfile.objects.get_or_create(user=user)
        return Response(
            {"detail": "Compte créé. Connectez-vous avec votre email et mot de passe."},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Auth"],
    summary="Connexion (JWT)",
    description="Accepte `email` + `password`, ou `phone_number` + `password` (ou `identifier` + `password`).",
)
class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ — Connexion (email/phone + password) → access + refresh tokens."""
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (LoginThrottle,)


@extend_schema(tags=["Auth"], summary="Rafraîchir le token")
class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh/ — Rafraîchir l'access token avec le refresh token."""
    permission_classes = (AllowAny,)
    throttle_classes = (TokenRefreshThrottle,)


@extend_schema(tags=["Auth"], summary="Profil utilisateur (GET/PUT)")
class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PUT /api/auth/profile/ — Profil de l'utilisateur connecté. Nécessite JWT."""
    serializer_class = ProfileSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def get(self, request, *args, **kwargs):
        if hasattr(request.user, "profile") and request.user.profile.user_type == UserProfile.USER_TYPE_PROFESSIONAL:
            request.user.profile.ensure_merchant_id()
        return super().get(request, *args, **kwargs)


# --- Password reset (forget password) & change password ---


@extend_schema(
    tags=["Auth"],
    summary="Mot de passe oublié — Demander un OTP",
    description="Envoie un code OTP par email. Utilisez ensuite POST /api/auth/password-reset/confirm/ avec ce code.",
    responses={200: {"description": "Si un compte existe pour cet email, un code OTP a été envoyé."}},
)
class PasswordResetRequestView(generics.GenericAPIView):
    """POST /api/auth/password-reset/ — Demande de réinitialisation (envoi OTP par email)."""
    serializer_class = PasswordResetRequestSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (PasswordResetThrottle,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        # Toujours renvoyer 200 pour ne pas révéler si l'email existe
        create_and_send_otp(email)
        return Response({
            "detail": "Si un compte existe pour cet email, un code OTP a été envoyé. Vérifiez votre boîte de réception (et les spams).",
        })


@extend_schema(
    tags=["Auth"],
    summary="Vérifier un code OTP",
    description="Vérifie que le code OTP est valide et non expiré (sans réinitialiser le mot de passe). Utile pour afficher l’écran « Nouveau mot de passe » après validation du code.",
    responses={
        200: {"description": "Code OTP valide."},
        400: {"description": "Code invalide ou expiré."},
    },
)
class VerifyOTPView(generics.GenericAPIView):
    """POST /api/auth/password-reset/verify/ — Vérifier un code OTP."""
    serializer_class = VerifyOTPSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (PasswordResetThrottle,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "Code OTP valide. Vous pouvez définir votre nouveau mot de passe."})


@extend_schema(
    tags=["Auth"],
    summary="Mot de passe oublié — Confirmer avec OTP",
    description="Vérifie le code OTP reçu par email et définit le nouveau mot de passe.",
    responses={200: {"description": "Mot de passe réinitialisé."}},
)
class PasswordResetConfirmView(generics.GenericAPIView):
    """POST /api/auth/password-reset/confirm/ — Confirmer avec OTP + nouveau mot de passe."""
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (PasswordResetThrottle,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        new_password = serializer.validated_data["new_password"]
        otp_record = serializer.validated_data["_otp_record"]

        user = get_user_model().objects.filter(email__iexact=email).first()
        if user:
            user.set_password(new_password)
            user.save()
        otp_record.delete()
        return Response({"detail": "Mot de passe réinitialisé. Vous pouvez vous connecter avec votre nouveau mot de passe."})


@extend_schema(
    tags=["Auth"],
    summary="Changer le mot de passe",
    description="Pour l'utilisateur connecté (JWT requis).",
    responses={200: {"description": "Mot de passe modifié."}},
)
class PasswordChangeView(generics.GenericAPIView):
    """POST /api/auth/password/change/ — Changer le mot de passe (utilisateur connecté)."""
    serializer_class = PasswordChangeSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "Mot de passe modifié."})
