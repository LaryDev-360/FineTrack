from django.conf import settings
from django.db import models


class Account(models.Model):
    """Compte / portefeuille (cash, banque, mobile money, épargne)."""

    ACCOUNT_TYPES = [
        ("cash", "Cash"),
        ("bank", "Bank Account"),
        ("mobile_money", "Mobile Money"),
        ("savings", "Savings"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    initial_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="XOF")
    color = models.CharField(max_length=7, default="#000000")
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_account"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"


class MobileMoneyWallet(models.Model):
    """
    Wallet mobile money d'un marchand, identifié par (provider, phone_number).

    L'idée : on sépare le solde par numéro (et par provider), tout en utilisant
    le modèle `Account` comme “porte-soldes” (current_balance).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_money_wallets",
    )
    provider = models.CharField(max_length=30, db_index=True)
    phone_number = models.CharField(max_length=30, db_index=True)

    # Le solde effectif (current_balance) vit dans `Account`.
    account = models.OneToOneField(
        Account,
        on_delete=models.CASCADE,
        related_name="mobile_money_wallet",
        unique=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_mobile_money_wallet"
        constraints = [
            models.UniqueConstraint(fields=["user", "provider", "phone_number"], name="uniq_mobile_money_wallet_per_user_provider_phone"),
        ]

    def save(self, *args, **kwargs):
        # Normalisation simple pour éviter les doublons “visuellement identiques”.
        if self.provider:
            self.provider = self.provider.strip().upper()
        if self.phone_number:
            self.phone_number = self.phone_number.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"MobileMoneyWallet({self.provider} {self.phone_number})"
