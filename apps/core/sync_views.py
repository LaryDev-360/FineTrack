"""Endpoint de synchronisation initiale (pull) pour un nouvel appareil ou réinstallation."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView

from apps.accounts.serializers import ProfileSerializer
from apps.budgets.serializers import BudgetSerializer
from apps.categories.serializers import CategorySerializer
from apps.transactions.serializers import TransactionSerializer

from .serializers import AccountSerializer, MobileMoneyWalletSerializer
from .user_snapshot import build_user_snapshot_data


class InitialSyncResponseSerializer(serializers.Serializer):
    """Schéma de réponse pour GET /api/sync/initial/."""

    generated_at = serializers.DateTimeField()
    user = ProfileSerializer()
    accounts = AccountSerializer(many=True)
    categories = CategorySerializer(many=True)
    transactions = TransactionSerializer(many=True)
    budgets = BudgetSerializer(many=True)
    mobile_money_wallets = MobileMoneyWalletSerializer(many=True)


@extend_schema(
    tags=["Synchronisation"],
    summary="Synchronisation initiale (pull)",
    description=(
        "Retourne en une requête les données de l’utilisateur connecté pour hydrater l’app "
        "(comptes, catégories, transactions, budgets, profil, wallets mobile money). "
        "À appeler après authentification sur un nouvel appareil. "
        "Les volumes peuvent être importants : prévoir une stratégie de pagination / delta sync plus tard si besoin."
    ),
    responses={200: InitialSyncResponseSerializer},
)
class InitialSyncView(APIView):
    """GET /api/sync/initial/ — Pull initial pour offline-first."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(build_user_snapshot_data(request.user, request))
