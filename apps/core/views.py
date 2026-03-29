from decimal import Decimal

from django.db import transaction as db_transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import UserProfile

from .models import Account, MobileMoneyWallet
from .serializers import (
    ACCOUNT_BULK_PAYLOAD_FIELDS,
    AccountBulkSyncRequestSerializer,
    AccountBulkSyncResponseSerializer,
    AccountSerializer,
    TransferSerializer,
    MobileMoneyWalletCreateSerializer,
    MobileMoneyWalletSerializer,
)
from .sync_bulk_helpers import (
    bulk_summary,
    parse_client_updated_at,
    split_bulk_item,
    validation_error_to_dict,
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

    @extend_schema(
        tags=["Comptes"],
        summary="Synchronisation groupée des comptes (offline → serveur)",
        description=(
            "Création ou mise à jour par lot. Même logique que pour les transactions : "
            "`client_updated_at` optionnel pour détecter les conflits (version serveur plus récente)."
        ),
        request=AccountBulkSyncRequestSerializer,
        responses={200: AccountBulkSyncResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="bulk-sync")
    def bulk_sync(self, request):
        outer = AccountBulkSyncRequestSerializer(data=request.data)
        outer.is_valid(raise_exception=True)
        raw_items = outer.validated_data["accounts"]
        results = []

        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                results.append(
                    {
                        "index": index,
                        "status": "error",
                        "id": None,
                        "client_id": "",
                        "local_id": "",
                        "errors": {"_item": ["Chaque entrée doit être un objet JSON."]},
                    }
                )
                continue

            try:
                pk, client_id, local_id, client_updated_at_raw, payload = split_bulk_item(
                    raw, ACCOUNT_BULK_PAYLOAD_FIELDS
                )
            except serializers.ValidationError as e:
                results.append(
                    {
                        "index": index,
                        "status": "error",
                        "id": None,
                        "client_id": str(raw.get("client_id", "") or ""),
                        "local_id": str(raw.get("local_id", "") or ""),
                        "errors": validation_error_to_dict(e),
                    }
                )
                continue

            base_meta = {"index": index, "client_id": client_id, "local_id": local_id}

            try:
                with db_transaction.atomic():
                    if pk is not None:
                        instance = (
                            Account.objects.select_for_update()
                            .filter(pk=pk, user=request.user)
                            .first()
                        )
                        if not instance:
                            results.append(
                                {
                                    **base_meta,
                                    "status": "error",
                                    "id": pk,
                                    "errors": {"id": ["Compte introuvable ou non autorisé."]},
                                }
                            )
                            continue

                        if client_updated_at_raw is not None:
                            try:
                                client_ts = parse_client_updated_at(client_updated_at_raw)
                            except serializers.ValidationError as e:
                                results.append(
                                    {
                                        **base_meta,
                                        "status": "error",
                                        "id": pk,
                                        "errors": validation_error_to_dict(e),
                                    }
                                )
                                continue
                            if instance.updated_at > client_ts:
                                results.append(
                                    {
                                        **base_meta,
                                        "status": "conflict",
                                        "id": instance.id,
                                        "errors": {
                                            "conflict": [
                                                "Une version plus récente existe sur le serveur. "
                                                "Fusionnez à partir de `server_account` puis renvoyez la mise à jour."
                                            ]
                                        },
                                        "server_account": AccountSerializer(
                                            instance, context={"request": request}
                                        ).data,
                                    }
                                )
                                continue

                        s = AccountSerializer(
                            instance,
                            data=payload,
                            partial=True,
                            context={"request": request},
                        )
                    else:
                        s = AccountSerializer(data=payload, context={"request": request})

                    if not s.is_valid():
                        results.append(
                            {
                                **base_meta,
                                "status": "error",
                                "id": pk,
                                "errors": dict(s.errors),
                            }
                        )
                        continue

                    try:
                        if pk is not None:
                            acc = s.save()
                        else:
                            acc = s.save(user=request.user)
                    except serializers.ValidationError as exc:
                        results.append(
                            {
                                **base_meta,
                                "status": "error",
                                "id": pk,
                                "errors": validation_error_to_dict(exc),
                            }
                        )
                        continue

                out = AccountSerializer(acc, context={"request": request}).data
                results.append(
                    {
                        **base_meta,
                        "status": "updated" if pk is not None else "created",
                        "id": acc.id,
                        "account": out,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        **base_meta,
                        "status": "error",
                        "id": pk,
                        "errors": {"detail": [str(e)]},
                    }
                )

        return Response(
            {"results": results, "summary": bulk_summary(results)},
            status=status.HTTP_200_OK,
        )

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
