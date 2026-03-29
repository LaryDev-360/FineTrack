"""Données agrégées utilisateur (sync initial, export JSON)."""

from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.serializers import ProfileSerializer
from apps.budgets.models import Budget
from apps.budgets.serializers import BudgetSerializer
from apps.categories.models import Category
from apps.categories.serializers import CategorySerializer
from apps.transactions.models import Transaction
from apps.transactions.serializers import TransactionSerializer

from .models import Account, MobileMoneyWallet
from .serializers import AccountSerializer, MobileMoneyWalletSerializer


def build_user_snapshot_data(user, request):
    """
    Construit le dict sérialisé (profil, comptes, catégories, transactions, budgets, wallets).
    `request` sert au contexte des serializers (URLs absolues si besoin).
    """
    if hasattr(user, "profile") and user.profile.user_type == UserProfile.USER_TYPE_PROFESSIONAL:
        user.profile.ensure_merchant_id()

    accounts = Account.objects.filter(user=user).order_by("-created_at")
    categories = Category.objects.filter(user=user).order_by("category_type", "name")
    transactions = (
        Transaction.objects.filter(user=user)
        .select_related("account", "category", "to_account")
        .order_by("-date", "-created_at")
    )
    budgets = Budget.objects.filter(user=user).select_related("category").order_by("-period_start")
    wallets = MobileMoneyWallet.objects.filter(user=user).select_related("account").order_by("-created_at")

    ctx = {"request": request}

    return {
        "generated_at": timezone.now(),
        "user": ProfileSerializer(user, context=ctx).data,
        "accounts": AccountSerializer(accounts, many=True, context=ctx).data,
        "categories": CategorySerializer(categories, many=True, context=ctx).data,
        "transactions": TransactionSerializer(transactions, many=True, context=ctx).data,
        "budgets": BudgetSerializer(budgets, many=True, context=ctx).data,
        "mobile_money_wallets": MobileMoneyWalletSerializer(wallets, many=True, context=ctx).data,
    }
