from decimal import Decimal
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import UserProfile

from .models import Account, MobileMoneyWallet
from .serializers import (
    AccountSerializer,
    TransferSerializer,
    MobileMoneyWalletCreateSerializer,
    MobileMoneyWalletSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Comptes"], summary="Liste des comptes"),
    create=extend_schema(tags=["Comptes"], summary="Créer un compte"),
    retrieve=extend_schema(tags=["Comptes"], summary="Détail d'un compte"),
    update=extend_schema(tags=["Comptes"], summary="Modifier un compte"),
    partial_update=extend_schema(tags=["Comptes"], summary="Modifier partiellement un compte"),
    destroy=extend_schema(tags=["Comptes"], summary="Supprimer un compte"),
)
class AccountViewSet(viewsets.ModelViewSet):
    """CRUD des comptes (portefeuilles). Uniquement les comptes de l'utilisateur connecté."""

    serializer_class = AccountSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(tags=["Comptes"], summary="Transfert entre deux comptes")
    @action(detail=False, methods=["post"], serializer_class=TransferSerializer)
    def transfer(self, request):
        """POST /api/accounts/transfer/ — Transfert d'un compte vers un autre (mise à jour des soldes)."""
        serializer = TransferSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        from_account = serializer.validated_data["_from_account"]
        to_account = serializer.validated_data["_to_account"]
        amount = serializer.validated_data["amount"]

        from_account.current_balance -= amount
        to_account.current_balance += amount
        from_account.save(update_fields=["current_balance", "updated_at"])
        to_account.save(update_fields=["current_balance", "updated_at"])

        return Response(
            {
                "detail": "Transfert effectué.",
                "from_account": {"id": from_account.id, "new_balance": str(from_account.current_balance)},
                "to_account": {"id": to_account.id, "new_balance": str(to_account.current_balance)},
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Mobile Money Wallets"],
        summary="Lister les wallets mobile money du marchand",
        responses={200: MobileMoneyWalletSerializer},
    ),
    create=extend_schema(
        tags=["Mobile Money Wallets"],
        summary="Créer un wallet mobile money (provider + numéro)",
        request=MobileMoneyWalletCreateSerializer,
        responses={201: MobileMoneyWalletSerializer},
    ),
)
class MobileMoneyWalletListCreateView(generics.ListCreateAPIView):
    """
    Endpoint marchand pour gérer les wallets (provider + numéro).
    Le solde est stocké dans l'`Account` relié.
    """

    permission_classes = (IsAuthenticated,)
    model = MobileMoneyWallet

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, "profile") or user.profile.user_type != UserProfile.USER_TYPE_PROFESSIONAL:
            raise PermissionDenied("Réservé aux comptes professionnels.")
        return MobileMoneyWallet.objects.filter(user=user).select_related("account")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MobileMoneyWalletCreateSerializer
        return MobileMoneyWalletSerializer
