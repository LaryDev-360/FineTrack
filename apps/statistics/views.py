"""Statistiques : synthèse, par catégorie, tendances."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Account
from apps.transactions.models import Transaction


def _format_trunc_period(value, gran: str) -> str:
    """Normalise la valeur renvoyée par TruncDate / TruncMonth selon le SGBD."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        s = str(value)
        return s[:10] if gran == "day" else s[:7]
    if gran == "day":
        return d.isoformat()
    return f"{d.year:04d}-{d.month:02d}"


def _parse_range_or_default(request):
    """Query params start_date / end_date (YYYY-MM-DD), sinon mois civil en cours jusqu’à aujourd’hui."""
    s = request.query_params.get("start_date")
    e = request.query_params.get("end_date")
    today = date.today()
    if s and e:
        sd = parse_date(str(s))
        ed = parse_date(str(e))
        if not sd or not ed:
            return None, None, Response(
                {"detail": "start_date et end_date doivent être au format YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if sd > ed:
            return None, None, Response(
                {"detail": "start_date doit être antérieure ou égale à end_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return sd, ed, None
    sd = date(today.year, today.month, 1)
    ed = today
    return sd, ed, None


def _base_tx_qs(user, sd, ed):
    return Transaction.objects.filter(
        user=user,
        date__date__gte=sd,
        date__date__lte=ed,
    )


class StatisticsSummaryResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_expense = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_income = serializers.DecimalField(max_digits=20, decimal_places=2)
    net = serializers.DecimalField(max_digits=20, decimal_places=2)
    counts = serializers.DictField()
    total_accounts_balance = serializers.DecimalField(max_digits=20, decimal_places=2)


@extend_schema(
    tags=["Statistiques"],
    summary="Synthèse (totaux dépenses / revenus / solde comptes)",
    parameters=[
        OpenApiParameter("start_date", str, description="Début période YYYY-MM-DD (optionnel, défaut : 1er du mois)"),
        OpenApiParameter("end_date", str, description="Fin période YYYY-MM-DD (optionnel, défaut : aujourd’hui)"),
    ],
    responses={200: StatisticsSummaryResponseSerializer},
)
class StatisticsSummaryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        sd, ed, err = _parse_range_or_default(request)
        if err:
            return err
        user = request.user
        qs = _base_tx_qs(user, sd, ed)

        total_expense = qs.filter(transaction_type="expense").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        total_income = qs.filter(transaction_type="income").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        net = total_income - total_expense

        counts = {
            "expense": qs.filter(transaction_type="expense").count(),
            "income": qs.filter(transaction_type="income").count(),
            "transfer": qs.filter(transaction_type="transfer").count(),
        }

        total_accounts_balance = (
            Account.objects.filter(user=user).aggregate(t=Sum("current_balance"))["t"] or Decimal("0")
        )

        return Response(
            {
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "total_expense": str(total_expense),
                "total_income": str(total_income),
                "net": str(net),
                "counts": counts,
                "total_accounts_balance": str(total_accounts_balance),
            }
        )


class CategoryBreakdownRowSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(allow_null=True)
    category_name = serializers.CharField(allow_blank=True)
    total = serializers.DecimalField(max_digits=20, decimal_places=2)
    percentage = serializers.FloatField()


class StatisticsByCategoryResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_expense = serializers.DecimalField(max_digits=20, decimal_places=2)
    by_category = CategoryBreakdownRowSerializer(many=True)


@extend_schema(
    tags=["Statistiques"],
    summary="Dépenses par catégorie",
    description="Répartition des dépenses (type expense) par catégorie sur la période.",
    parameters=[
        OpenApiParameter("start_date", str, description="YYYY-MM-DD (optionnel)"),
        OpenApiParameter("end_date", str, description="YYYY-MM-DD (optionnel)"),
    ],
    responses={200: StatisticsByCategoryResponseSerializer},
)
class StatisticsByCategoryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        sd, ed, err = _parse_range_or_default(request)
        if err:
            return err
        user = request.user
        qs = _base_tx_qs(user, sd, ed).filter(transaction_type="expense")

        total_expense = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

        rows = (
            qs.values("category_id", "category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        by_cat = []
        for row in rows:
            cid = row["category_id"]
            name = row["category__name"] or "(Sans catégorie)"
            tot = row["total"] or Decimal("0")
            pct = float((tot / total_expense) * 100) if total_expense > 0 else 0.0
            by_cat.append(
                {
                    "category_id": cid,
                    "category_name": name,
                    "total": str(tot),
                    "percentage": round(pct, 2),
                }
            )

        return Response(
            {
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "total_expense": str(total_expense),
                "by_category": by_cat,
            }
        )


class TrendPointSerializer(serializers.Serializer):
    period = serializers.CharField()
    expense = serializers.DecimalField(max_digits=20, decimal_places=2)
    income = serializers.DecimalField(max_digits=20, decimal_places=2)
    net = serializers.DecimalField(max_digits=20, decimal_places=2)


class StatisticsTrendsResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    granularity = serializers.CharField()
    points = TrendPointSerializer(many=True)


@extend_schema(
    tags=["Statistiques"],
    summary="Tendances (dépenses / revenus par jour ou par mois)",
    parameters=[
        OpenApiParameter("start_date", str, description="YYYY-MM-DD (optionnel)"),
        OpenApiParameter("end_date", str, description="YYYY-MM-DD (optionnel)"),
        OpenApiParameter(
            "granularity",
            str,
            description="`day` (défaut) ou `month`",
        ),
    ],
    responses={200: StatisticsTrendsResponseSerializer},
)
class StatisticsTrendsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        sd, ed, err = _parse_range_or_default(request)
        if err:
            return err
        user = request.user
        gran = (request.query_params.get("granularity") or "day").lower()
        if gran not in ("day", "month"):
            return Response(
                {"detail": "granularity doit être day ou month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = _base_tx_qs(user, sd, ed)
        trunc = TruncDate("date") if gran == "day" else TruncMonth("date")

        expense_rows = (
            qs.filter(transaction_type="expense")
            .annotate(period=trunc)
            .values("period")
            .annotate(total=Sum("amount"))
        )
        income_rows = (
            qs.filter(transaction_type="income")
            .annotate(period=trunc)
            .values("period")
            .annotate(total=Sum("amount"))
        )

        merged = defaultdict(lambda: {"expense": Decimal("0"), "income": Decimal("0")})
        for row in expense_rows:
            pk = _format_trunc_period(row["period"], gran)
            merged[pk]["expense"] = row["total"] or Decimal("0")
        for row in income_rows:
            pk = _format_trunc_period(row["period"], gran)
            merged[pk]["income"] = row["total"] or Decimal("0")

        points = []
        for period in sorted(merged.keys()):
            ex = merged[period]["expense"]
            inc = merged[period]["income"]
            points.append(
                {
                    "period": period,
                    "expense": str(ex),
                    "income": str(inc),
                    "net": str(inc - ex),
                }
            )

        return Response(
            {
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "granularity": gran,
                "points": points,
            }
        )
