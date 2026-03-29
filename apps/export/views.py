"""Export CSV (transactions) et JSON (sauvegarde complète)."""

import csv

from django.http import HttpResponse
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Account
from apps.core.sync_views import InitialSyncResponseSerializer
from apps.core.user_snapshot import build_user_snapshot_data
from apps.transactions.models import Transaction


class ExportBackupResponseSerializer(InitialSyncResponseSerializer):
    """Schéma GET /api/export/json/ (identique au sync initial + export_type)."""

    export_type = serializers.CharField()


def _transactions_for_export(user, request):
    """
    Transactions de l'utilisateur, optionnellement filtrées par période (start_date + end_date)
    et/ou par account_id (compte appartenant à l'utilisateur).
    """
    qs = (
        Transaction.objects.filter(user=user)
        .select_related("account", "category", "to_account")
        .order_by("-date", "-created_at")
    )

    sd = request.query_params.get("start_date")
    ed = request.query_params.get("end_date")
    if sd or ed:
        if not sd or not ed:
            return None, Response(
                {"detail": "Fournir start_date et end_date ensemble (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        d1 = parse_date(str(sd))
        d2 = parse_date(str(ed))
        if not d1 or not d2:
            return None, Response(
                {"detail": "start_date et end_date doivent être au format YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if d1 > d2:
            return None, Response(
                {"detail": "start_date doit être antérieure ou égale à end_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(date__date__gte=d1, date__date__lte=d2)

    aid = request.query_params.get("account_id")
    if aid:
        try:
            aid_int = int(aid)
        except (TypeError, ValueError):
            return None, Response(
                {"detail": "account_id doit être un entier."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not Account.objects.filter(pk=aid_int, user=user).exists():
            return None, Response(
                {"detail": "Compte introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        qs = qs.filter(account_id=aid_int)

    return qs, None


@extend_schema(
    tags=["Export"],
    summary="Export CSV des transactions",
    description=(
        "Télécharge un fichier CSV (UTF-8). Sans filtres : toutes les transactions. "
        "Optionnel : `start_date` + `end_date` (YYYY-MM-DD), `account_id`."
    ),
    parameters=[
        OpenApiParameter("start_date", str, description="Début période (avec end_date)"),
        OpenApiParameter("end_date", str, description="Fin période (avec start_date)"),
        OpenApiParameter("account_id", int, description="Limiter au compte (doit vous appartenir)"),
    ],
    responses={(200, "text/csv"): OpenApiTypes.BINARY},
)
class ExportTransactionsCSVView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        qs, err = _transactions_for_export(request.user, request)
        if err:
            return err

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="finetrack_transactions.csv"'
        response.write("\ufeff")  # BOM Excel

        w = csv.writer(response)
        w.writerow(
            [
                "id",
                "date",
                "transaction_type",
                "amount",
                "account_id",
                "account_name",
                "category_id",
                "category_name",
                "to_account_id",
                "to_account_name",
                "note",
                "created_at",
                "updated_at",
            ]
        )
        for tx in qs:
            w.writerow(
                [
                    tx.pk,
                    tx.date.isoformat(),
                    tx.transaction_type,
                    str(tx.amount),
                    tx.account_id,
                    tx.account.name,
                    tx.category_id or "",
                    tx.category.name if tx.category else "",
                    tx.to_account_id or "",
                    tx.to_account.name if tx.to_account else "",
                    tx.note.replace("\r\n", " ").replace("\n", " ") if tx.note else "",
                    tx.created_at.isoformat(),
                    tx.updated_at.isoformat(),
                ]
            )
        return response


@extend_schema(
    tags=["Export"],
    summary="Export JSON (sauvegarde complète)",
    description=(
        "Même contenu structurel que la synchronisation initiale (profil, comptes, catégories, "
        "transactions, budgets, wallets), avec `export_type` et `generated_at`."
    ),
    responses={200: ExportBackupResponseSerializer},
)
class ExportBackupJSONView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        data = build_user_snapshot_data(request.user, request)
        data["export_type"] = "full_backup"
        resp = Response(data)
        resp["Content-Disposition"] = 'attachment; filename="finetrack_backup.json"'
        return resp
