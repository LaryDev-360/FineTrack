from django.db import transaction as db_transaction
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

from .models import Budget
from .serializers import (
    BUDGET_BULK_PAYLOAD_FIELDS,
    BudgetBulkSyncRequestSerializer,
    BudgetBulkSyncResponseSerializer,
    BudgetSerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=["Budgets"],
        summary="Liste des budgets",
        parameters=[
            OpenApiParameter("category_id", int, description="Filtrer par catégorie (id)"),
            OpenApiParameter(
                "is_global",
                str,
                description="true / false : budgets globaux ou par catégorie",
            ),
            OpenApiParameter(
                "active_on",
                str,
                description="Date YYYY-MM-DD : budgets dont la période contient ce jour (inclus)",
            ),
        ],
    ),
    create=extend_schema(tags=["Budgets"], summary="Créer un budget"),
    retrieve=extend_schema(tags=["Budgets"], summary="Détail d'un budget"),
    update=extend_schema(tags=["Budgets"], summary="Modifier un budget"),
    partial_update=extend_schema(tags=["Budgets"], summary="Modifier partiellement un budget"),
    destroy=extend_schema(tags=["Budgets"], summary="Supprimer un budget"),
)
class BudgetViewSet(viewsets.ModelViewSet):
    """CRUD des budgets (global ou par catégorie, sur une période)."""

    serializer_class = BudgetSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Budget.objects.filter(user=self.request.user).select_related("category")
        p = self.request.query_params

        if cid := p.get("category_id"):
            try:
                qs = qs.filter(category_id=int(cid))
            except ValueError:
                pass

        if (ig := p.get("is_global")) is not None:
            v = str(ig).lower()
            if v in ("true", "1", "yes"):
                qs = qs.filter(is_global=True)
            elif v in ("false", "0", "no"):
                qs = qs.filter(is_global=False)

        if active_on := p.get("active_on"):
            d = parse_date(str(active_on))
            if d:
                qs = qs.filter(period_start__lte=d, period_end__gte=d)

        return qs

    @extend_schema(
        tags=["Budgets"],
        summary="Synchronisation groupée des budgets (offline → serveur)",
        description="Création ou mise à jour par lot ; `client_updated_at` optionnel pour les conflits.",
        request=BudgetBulkSyncRequestSerializer,
        responses={200: BudgetBulkSyncResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="bulk-sync")
    def bulk_sync(self, request):
        outer = BudgetBulkSyncRequestSerializer(data=request.data)
        outer.is_valid(raise_exception=True)
        raw_items = outer.validated_data["budgets"]
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
                    raw, BUDGET_BULK_PAYLOAD_FIELDS
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
                            Budget.objects.select_for_update()
                            .filter(pk=pk, user=request.user)
                            .first()
                        )
                        if not instance:
                            results.append(
                                {
                                    **base_meta,
                                    "status": "error",
                                    "id": pk,
                                    "errors": {"id": ["Budget introuvable ou non autorisé."]},
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
                                                "Fusionnez à partir de `server_budget` puis renvoyez la mise à jour."
                                            ]
                                        },
                                        "server_budget": BudgetSerializer(
                                            instance, context={"request": request}
                                        ).data,
                                    }
                                )
                                continue

                        s = BudgetSerializer(
                            instance,
                            data=payload,
                            partial=True,
                            context={"request": request},
                        )
                    else:
                        s = BudgetSerializer(data=payload, context={"request": request})

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
                            obj = s.save()
                        else:
                            obj = s.save(user=request.user)
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

                out = BudgetSerializer(obj, context={"request": request}).data
                results.append(
                    {
                        **base_meta,
                        "status": "updated" if pk is not None else "created",
                        "id": obj.id,
                        "budget": out,
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
