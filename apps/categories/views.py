from django.db import transaction as db_transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
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

from .models import Category
from .serializers import (
    CATEGORY_BULK_PAYLOAD_FIELDS,
    CategoryBulkSyncRequestSerializer,
    CategoryBulkSyncResponseSerializer,
    CategorySerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Catégories"], summary="Liste des catégories"),
    create=extend_schema(tags=["Catégories"], summary="Créer une catégorie"),
    retrieve=extend_schema(tags=["Catégories"], summary="Détail d'une catégorie"),
    update=extend_schema(tags=["Catégories"], summary="Modifier une catégorie"),
    partial_update=extend_schema(tags=["Catégories"], summary="Modifier partiellement une catégorie"),
    destroy=extend_schema(tags=["Catégories"], summary="Supprimer une catégorie"),
)
class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD des catégories. Uniquement les catégories de l'utilisateur connecté."""

    serializer_class = CategorySerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        tags=["Catégories"],
        summary="Synchronisation groupée des catégories (offline → serveur)",
        description="Création ou mise à jour par lot ; `client_updated_at` optionnel pour les conflits.",
        request=CategoryBulkSyncRequestSerializer,
        responses={200: CategoryBulkSyncResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="bulk-sync")
    def bulk_sync(self, request):
        outer = CategoryBulkSyncRequestSerializer(data=request.data)
        outer.is_valid(raise_exception=True)
        raw_items = outer.validated_data["categories"]
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
                    raw, CATEGORY_BULK_PAYLOAD_FIELDS
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
                            Category.objects.select_for_update()
                            .filter(pk=pk, user=request.user)
                            .first()
                        )
                        if not instance:
                            results.append(
                                {
                                    **base_meta,
                                    "status": "error",
                                    "id": pk,
                                    "errors": {"id": ["Catégorie introuvable ou non autorisée."]},
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
                                                "Fusionnez à partir de `server_category` puis renvoyez la mise à jour."
                                            ]
                                        },
                                        "server_category": CategorySerializer(
                                            instance, context={"request": request}
                                        ).data,
                                    }
                                )
                                continue

                        s = CategorySerializer(
                            instance,
                            data=payload,
                            partial=True,
                            context={"request": request},
                        )
                    else:
                        s = CategorySerializer(data=payload, context={"request": request})

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

                out = CategorySerializer(obj, context={"request": request}).data
                results.append(
                    {
                        **base_meta,
                        "status": "updated" if pk is not None else "created",
                        "id": obj.id,
                        "category": out,
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
