"""Comptabilité automatisée et bilans (cahier des charges : sections 6 et 7)."""

import csv
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transactions.models import Transaction

from .serializers import (
    AccountingBilansResponseSerializer,
    AccountingKPIsResponseSerializer,
    AccountingPeriodResponseSerializer,
)
from .services import (
    aggregate_income_expense_net,
    average_ticket_income,
    coefficient_of_variation_revenue,
    daily_income_totals,
    growth_ratio,
    iterate_bilan_buckets,
    period_bounds_day_week_month_year,
    previous_period_same_length,
    top_activity_days,
    volume_transactions_non_transfer,
)


def _parse_date_param(request, name: str, default: date | None) -> tuple[date | None, Response | None]:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        if default is None:
            return None, Response(
                {"detail": f"Paramètre {name} requis (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return default, None
    d = parse_date(str(raw))
    if not d:
        return None, Response(
            {"detail": f"{name} doit être au format YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return d, None


def _prev_calendar_month(last_day_of_month: date) -> tuple[date, date]:
    """Dernier jour du mois précédent + premier jour du mois précédent."""
    first_this = date(last_day_of_month.year, last_day_of_month.month, 1)
    prev_last = first_this - timedelta(days=1)
    prev_first = date(prev_last.year, prev_last.month, 1)
    return prev_first, prev_last


@extend_schema(
    tags=["Comptabilité"],
    summary="Instantané comptable pour une période (jour / semaine / mois / année)",
    description=(
        "Aligné sur le cahier des charges §6.2 : agrégats journaliers, hebdomadaires, mensuels ou annuels. "
        "Semaine = semaine ISO (lundi–dimanche). "
        "Pour le mois : croissance vs le mois civil précédent. "
        "Pour l’année : moyenne mensuelle de CA et évolution vs l’année civile précédente."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            str,
            description="`day`, `week`, `month` ou `year`",
            required=True,
        ),
        OpenApiParameter(
            "reference_date",
            str,
            description="Date de référence YYYY-MM-DD (défaut : aujourd’hui)",
        ),
    ],
    responses={200: AccountingPeriodResponseSerializer},
)
class AccountingPeriodView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        gran = (request.query_params.get("granularity") or "").lower()
        if gran not in ("day", "week", "month", "year"):
            return Response(
                {"detail": "granularity doit être day, week, month ou year."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        today = date.today()
        ref, err = _parse_date_param(request, "reference_date", today)
        if err:
            return err

        try:
            start, end = period_bounds_day_week_month_year(gran, ref)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        agg = aggregate_income_expense_net(user, start, end)
        details: dict = {}

        if gran == "week":
            details["volume_transactions"] = volume_transactions_non_transfer(user, start, end)
            details["jours_forte_activite"] = top_activity_days(user, start, end, n=3)

        if gran == "month":
            p0, p1 = _prev_calendar_month(end)
            prev = aggregate_income_expense_net(user, p0, p1)
            ca = agg["chiffre_affaires"]
            prev_ca = prev["chiffre_affaires"]
            details["chiffre_affaires_periode_precedente"] = prev_ca
            details["croissance_vs_periode_precedente_pct"] = growth_ratio(ca, prev_ca)

        if gran == "year":
            months = 12
            ca = agg["chiffre_affaires"]
            details["moyenne_mensuelle_chiffre_affaires"] = ca / Decimal(months) if months else Decimal("0")
            py = ref.year - 1
            prev_s, prev_e = date(py, 1, 1), date(py, 12, 31)
            prev_y = aggregate_income_expense_net(user, prev_s, prev_e)
            details["evolution_vs_annee_precedente_pct"] = growth_ratio(ca, prev_y["chiffre_affaires"])

        return Response(
            {
                "granularity": gran,
                "reference_date": ref.isoformat(),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "chiffre_affaires": str(agg["chiffre_affaires"]),
                "depenses": str(agg["depenses"]),
                "resultat_net": str(agg["resultat_net"]),
                "nombre_transactions": agg["nombre_transactions"],
                "details": details,
            }
        )


@extend_schema(
    tags=["Comptabilité"],
    summary="Série de bilans sur une plage (bilan journalier à annuel)",
    description=(
        "§7 du cahier des charges : une ligne par sous-période (jour, semaine ISO, mois ou année) "
        "entre start_date et end_date, avec CA, dépenses et résultat net."
    ),
    parameters=[
        OpenApiParameter("granularity", str, description="`daily`, `weekly`, `monthly` ou `annual`", required=True),
        OpenApiParameter("start_date", str, required=True),
        OpenApiParameter("end_date", str, required=True),
    ],
    responses={200: AccountingBilansResponseSerializer},
)
class AccountingBilansView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        gran = (request.query_params.get("granularity") or "").lower()
        if gran not in ("daily", "weekly", "monthly", "annual"):
            return Response(
                {"detail": "granularity doit être daily, weekly, monthly ou annual."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sd, err = _parse_date_param(request, "start_date", None)
        if err:
            return err
        ed, err = _parse_date_param(request, "end_date", None)
        if err:
            return err
        assert sd is not None and ed is not None
        if sd > ed:
            return Response(
                {"detail": "start_date doit être antérieure ou égale à end_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            buckets = iterate_bilan_buckets(gran, sd, ed)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        periods = []
        for bs, be, label in buckets:
            agg = aggregate_income_expense_net(user, bs, be)
            periods.append(
                {
                    "label": label,
                    "start_date": bs.isoformat(),
                    "end_date": be.isoformat(),
                    "chiffre_affaires": str(agg["chiffre_affaires"]),
                    "depenses": str(agg["depenses"]),
                    "resultat_net": str(agg["resultat_net"]),
                    "nombre_transactions": agg["nombre_transactions"],
                }
            )

        return Response(
            {
                "granularity": gran,
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "periods": periods,
            }
        )


@extend_schema(
    tags=["Comptabilité"],
    summary="Indicateurs clés (§6.3) sur une plage",
    description=(
        "Ticket moyen sur les revenus, nombre de transactions, croissance du CA vs la période précédente "
        "de même durée, variabilité des revenus (coefficient de variation des journées)."
    ),
    parameters=[
        OpenApiParameter("start_date", str, required=True),
        OpenApiParameter("end_date", str, required=True),
    ],
    responses={200: AccountingKPIsResponseSerializer},
)
class AccountingKPIsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        sd, err = _parse_date_param(request, "start_date", None)
        if err:
            return err
        ed, err = _parse_date_param(request, "end_date", None)
        if err:
            return err
        assert sd is not None and ed is not None
        if sd > ed:
            return Response(
                {"detail": "start_date doit être antérieure ou égale à end_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        length_days = (ed - sd).days + 1
        prev_start, prev_end = previous_period_same_length(sd, length_days)

        qs_cur = Transaction.objects.filter(
            user=user,
            date__date__gte=sd,
            date__date__lte=ed,
        )
        qs_prev = Transaction.objects.filter(
            user=user,
            date__date__gte=prev_start,
            date__date__lte=prev_end,
        )

        ca_cur = qs_cur.filter(transaction_type="income").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        ca_prev = qs_prev.filter(transaction_type="income").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        ntx = qs_cur.exclude(transaction_type="transfer").count()
        ticket = average_ticket_income(user, sd, ed)
        daily = daily_income_totals(user, sd, ed)
        var_cv = coefficient_of_variation_revenue(daily)

        return Response(
            {
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "nombre_transactions": ntx,
                "ticket_moyen_revenus": str(ticket) if ticket is not None else None,
                "taux_croissance_chiffre_affaires_pct": growth_ratio(ca_cur, ca_prev),
                "variabilite_revenus_coefficient": var_cv,
                "chiffre_affaires_total": str(ca_cur),
                "chiffre_affaires_periode_precedente": str(ca_prev),
            }
        )


@extend_schema(
    tags=["Comptabilité"],
    summary="Export CSV des bilans (série sur une plage)",
    description="Même logique que GET /api/accounting/bilans/ ; fichier CSV pour tableur ou pièce jointe.",
    parameters=[
        OpenApiParameter("granularity", str, description="`daily`, `weekly`, `monthly` ou `annual`", required=True),
        OpenApiParameter("start_date", str, required=True),
        OpenApiParameter("end_date", str, required=True),
    ],
    responses={(200, "text/csv"): OpenApiTypes.BINARY},
)
class AccountingBilanExportCSVView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        gran = (request.query_params.get("granularity") or "").lower()
        if gran not in ("daily", "weekly", "monthly", "annual"):
            return Response(
                {"detail": "granularity doit être daily, weekly, monthly ou annual."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sd, err = _parse_date_param(request, "start_date", None)
        if err:
            return err
        ed, err = _parse_date_param(request, "end_date", None)
        if err:
            return err
        assert sd is not None and ed is not None
        if sd > ed:
            return Response(
                {"detail": "start_date doit être antérieure ou égale à end_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            buckets = iterate_bilan_buckets(gran, sd, ed)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="finetrack_bilans.csv"'
        response.write("\ufeff")
        w = csv.writer(response)
        w.writerow(
            [
                "label",
                "start_date",
                "end_date",
                "chiffre_affaires",
                "depenses",
                "resultat_net",
                "nombre_transactions",
            ]
        )
        for bs, be, label in buckets:
            agg = aggregate_income_expense_net(user, bs, be)
            w.writerow(
                [
                    label,
                    bs.isoformat(),
                    be.isoformat(),
                    str(agg["chiffre_affaires"]),
                    str(agg["depenses"]),
                    str(agg["resultat_net"]),
                    agg["nombre_transactions"],
                ]
            )
        return response
