"""Agrégations comptables (revenus, dépenses, bilans) à partir des transactions."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from apps.transactions.models import Transaction


def period_bounds_day_week_month_year(granularity: str, ref: date) -> tuple[date, date]:
    """Bornes inclusives pour jour / semaine ISO (lun–dim) / mois civil / année civile."""
    g = granularity.lower()
    if g == "day":
        return ref, ref
    if g == "week":
        start = ref - timedelta(days=ref.weekday())
        return start, start + timedelta(days=6)
    if g == "month":
        last = monthrange(ref.year, ref.month)[1]
        return date(ref.year, ref.month, 1), date(ref.year, ref.month, last)
    if g == "year":
        return date(ref.year, 1, 1), date(ref.year, 12, 31)
    raise ValueError(f"granularity inconnue: {granularity}")


def _tx_base(user, start: date, end: date):
    return Transaction.objects.filter(
        user=user,
        date__date__gte=start,
        date__date__lte=end,
    )


def aggregate_income_expense_net(user, start: date, end: date) -> dict:
    qs = _tx_base(user, start, end)
    income = qs.filter(transaction_type="income").aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense = qs.filter(transaction_type="expense").aggregate(t=Sum("amount"))["t"] or Decimal("0")
    n = qs.exclude(transaction_type="transfer").count()
    return {
        "chiffre_affaires": income,
        "depenses": expense,
        "charges": expense,
        "resultat_net": income - expense,
        "profit": income - expense,
        "nombre_transactions": n,
    }


def volume_transactions_non_transfer(user, start: date, end: date) -> int:
    return (
        _tx_base(user, start, end)
        .exclude(transaction_type="transfer")
        .count()
    )


def top_activity_days(user, start: date, end: date, n: int = 3) -> list[dict]:
    """Jours avec le plus d’opérations (hors transfert), pour bilans hebdomadaires."""
    qs = (
        _tx_base(user, start, end)
        .exclude(transaction_type="transfer")
        .annotate(d=TruncDate("date"))
        .values("d")
        .annotate(nombre_transactions=Count("id"))
        .order_by("-nombre_transactions")[:n]
    )
    out = []
    for row in qs:
        d = row["d"]
        ds = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        out.append({"date": ds, "nombre_transactions": row["nombre_transactions"]})
    return out


def previous_period_same_length(before_start: date, length_days: int) -> tuple[date, date]:
    end = before_start - timedelta(days=1)
    start = end - timedelta(days=length_days - 1)
    return start, end


def growth_ratio(current: Decimal, previous: Decimal) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return float(((current - previous) / previous) * 100)


def _norm_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    return d


def daily_income_totals(user, start: date, end: date) -> list[Decimal]:
    """Un total revenus par jour calendaire (0 si aucun)."""
    qs = (
        _tx_base(user, start, end)
        .filter(transaction_type="income")
        .annotate(d=TruncDate("date"))
        .values("d")
        .annotate(total=Sum("amount"))
    )
    by_day: dict[date, Decimal] = {}
    for row in qs:
        d = _norm_date(row["d"])
        by_day[d] = row["total"] or Decimal("0")
    out = []
    d = start
    while d <= end:
        out.append(by_day.get(d, Decimal("0")))
        d += timedelta(days=1)
    return out


def coefficient_of_variation_revenue(daily_incomes: list[Decimal]) -> float | None:
    """Variabilité des revenus : écart-type / moyenne (sur les jours)."""
    if not daily_incomes:
        return None
    vals = [float(x) for x in daily_incomes]
    m = mean(vals)
    if m == 0:
        return None
    if len(vals) < 2:
        return 0.0
    return pstdev(vals) / m


def average_ticket_income(user, start: date, end: date) -> Decimal | None:
    qs = _tx_base(user, start, end).filter(transaction_type="income")
    n = qs.count()
    if n == 0:
        return None
    total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    return total / n


def iterate_bilan_buckets(
    granularity: str, start: date, end: date
) -> list[tuple[date, date, str]]:
    """
    Retourne une liste de (début, fin, libellé) pour chaque sous-période dans [start, end].
    granularité : daily | weekly | monthly | annual
    """
    g = granularity.lower()
    buckets: list[tuple[date, date, str]] = []
    if start > end:
        return buckets

    if g == "daily":
        d = start
        while d <= end:
            buckets.append((d, d, d.isoformat()))
            d += timedelta(days=1)
        return buckets

    if g == "weekly":
        # aligner sur le lundi de la semaine de `start`
        cur = start - timedelta(days=start.weekday())
        while cur <= end:
            wk_end = cur + timedelta(days=6)
            seg_start = max(cur, start)
            seg_end = min(wk_end, end)
            if seg_start <= seg_end:
                iso = seg_start.isocalendar()
                label = f"{iso.year}-W{iso.week:02d}"
                buckets.append((seg_start, seg_end, label))
            cur += timedelta(days=7)
        return buckets

    if g == "monthly":
        y, m = start.year, start.month
        while True:
            first = date(y, m, 1)
            last_d = monthrange(y, m)[1]
            last = date(y, m, last_d)
            seg_start = max(first, start)
            seg_end = min(last, end)
            if seg_start <= seg_end:
                label = f"{y:04d}-{m:02d}"
                buckets.append((seg_start, seg_end, label))
            if seg_end >= end:
                break
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1
        return buckets

    if g == "annual":
        y = start.year
        while y <= end.year:
            first = date(y, 1, 1)
            last = date(y, 12, 31)
            seg_start = max(first, start)
            seg_end = min(last, end)
            if seg_start <= seg_end:
                buckets.append((seg_start, seg_end, str(y)))
            y += 1
        return buckets

    raise ValueError(f"granularity inconnue: {granularity}")
