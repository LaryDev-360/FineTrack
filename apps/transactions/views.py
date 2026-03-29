from django.db import transaction
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.sync_bulk_helpers import (
    bulk_summary,
    parse_client_updated_at,
    split_bulk_item,
    validation_error_to_dict,
)

from .models import Transaction
from .serializers import (
    TRANSACTION_PAYLOAD_FIELDS,
    BulkSyncRequestSerializer,
    BulkSyncResponseSerializer,
    TransactionSerializer,
)
from .services import reverse_transaction_effect


@extend_schema_view(
    list=extend_schema(
        tags=["Transactions"],
        summary="Liste des transactions",
        parameters=[
            OpenApiParameter("account_id", int, description="Filtrer par compte source (id)"),
            OpenApiParameter("category_id", int, description="Filtrer par catégorie (id)"),
            OpenApiParameter(
                "transaction_type",
                str,
                description="Filtrer par type : expense, income, transfer",
            ),
            OpenApiParameter("date_from", str, description="Date début (YYYY-MM-DD), sur le champ date"),
            OpenApiParameter("date_to", str, description="Date fin (YYYY-MM-DD), sur le champ date"),
        ],
    ),
    create=extend_schema(tags=["Transactions"], summary="Créer une transaction"),
    retrieve=extend_schema(tags=["Transactions"], summary="Détail d'une transaction"),
    update=extend_schema(tags=["Transactions"], summary="Modifier une transaction"),
    partial_update=extend_schema(tags=["Transactions"], summary="Modifier partiellement une transaction"),
    destroy=extend_schema(tags=["Transactions"], summary="Supprimer une transaction"),
)
class TransactionViewSet(viewsets.ModelViewSet):
    """
    CRUD des transactions (dépense, revenu, transfert).

    Les soldes des comptes (`Account.current_balance`) sont mis à jour automatiquement.
    """

    serializer_class = TransactionSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user).select_related(
            "account", "category", "to_account"
        )

        p = self.request.query_params
        if aid := p.get("account_id"):
            try:
                qs = qs.filter(account_id=int(aid))
            except ValueError:
                pass
        if cid := p.get("category_id"):
            try:
                qs = qs.filter(category_id=int(cid))
            except ValueError:
                pass
        if ttype := p.get("transaction_type"):
            if ttype in ("expense", "income", "transfer"):
                qs = qs.filter(transaction_type=ttype)
        if df := p.get("date_from"):
            d = parse_date(df)
            if d:
                qs = qs.filter(date__date__gte=d)
        if dt := p.get("date_to"):
            d = parse_date(dt)
            if d:
                qs = qs.filter(date__date__lte=d)

        return qs

    @extend_schema(
        tags=["Transactions"],
        summary="Synchronisation groupée (offline → serveur)",
        description=(
            "Envoie une liste de transactions à créer (sans `id` ou `id: null`) ou à mettre à jour (`id` = id serveur). "
            "Chaque entrée peut inclure `client_id` / `local_id` pour corrélation côté app. "
            "Pour les **mises à jour**, vous pouvez envoyer `client_updated_at` (valeur de `updated_at` "
            "connue au moment de l’édition) : si le serveur a une version plus récente, la ligne est en "
            "`status: conflict` avec `server_transaction` (aucune écriture). "
            "Si `client_updated_at` est absent, la mise à jour est appliquée comme avant (pas de contrôle de conflit). "
            "Les entrées valides sont enregistrées une par une ; les erreurs n’annulent pas les autres."
        ),
        request=BulkSyncRequestSerializer,
        responses={200: BulkSyncResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="bulk-sync")
    def bulk_sync(self, request):
        outer = BulkSyncRequestSerializer(data=request.data)
        outer.is_valid(raise_exception=True)
        raw_items = outer.validated_data["transactions"]
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
                    raw, TRANSACTION_PAYLOAD_FIELDS
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

            base_meta = {
                "index": index,
                "client_id": client_id,
                "local_id": local_id,
            }

            try:
                with transaction.atomic():
                    if pk is not None:
                        instance = (
                            Transaction.objects.select_for_update()
                            .filter(pk=pk, user=request.user)
                            .first()
                        )
                        if not instance:
                            results.append(
                                {
                                    **base_meta,
                                    "status": "error",
                                    "id": pk,
                                    "errors": {"id": ["Transaction introuvable ou non autorisée."]},
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
                                                "Fusionnez à partir de `server_transaction` puis renvoyez la mise à jour."
                                            ]
                                        },
                                        "server_transaction": TransactionSerializer(
                                            instance, context={"request": request}
                                        ).data,
                                    }
                                )
                                continue

                        s = TransactionSerializer(
                            instance,
                            data=payload,
                            partial=True,
                            context={"request": request},
                        )
                    else:
                        s = TransactionSerializer(data=payload, context={"request": request})

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
                        tx = s.save()
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

                    tx.is_synced = True
                    tx.save(update_fields=["is_synced"])

                out = TransactionSerializer(tx, context={"request": request}).data
                results.append(
                    {
                        **base_meta,
                        "status": "updated" if pk is not None else "created",
                        "id": tx.id,
                        "transaction": out,
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

    @transaction.atomic
    def perform_destroy(self, instance):
        reverse_transaction_effect(instance)
        instance.delete()
