from decimal import Decimal
from rest_framework import serializers

from apps.accounts.models import UserProfile
from .models import Account, MobileMoneyWallet

# Champs autorisés dans le payload bulk-sync (hors meta client_id / local_id / client_updated_at / id)
ACCOUNT_BULK_PAYLOAD_FIELDS = frozenset(
    {
        "name",
        "account_type",
        "initial_balance",
        "current_balance",
        "currency",
        "color",
        "icon",
        "is_active",
    }
)


class AccountSerializer(serializers.ModelSerializer):
    """CRUD Comptes (portefeuilles)."""

    class Meta:
        model = Account
        fields = (
            "id",
            "name",
            "account_type",
            "initial_balance",
            "current_balance",
            "currency",
            "color",
            "icon",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "name": {"max_length": 100},
            "color": {"max_length": 7},
            "icon": {"max_length": 50},
            "currency": {"max_length": 3},
        }

    def create(self, validated_data):
        # À la création, current_balance = initial_balance
        validated_data["current_balance"] = validated_data.get("initial_balance", Decimal("0"))
        return super().create(validated_data)


class TransferSerializer(serializers.Serializer):
    """Transfert entre deux comptes (mise à jour des soldes uniquement)."""

    from_account_id = serializers.IntegerField(required=True)
    to_account_id = serializers.IntegerField(required=True)
    amount = serializers.DecimalField(required=True, max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value

    def validate(self, attrs):
        from_account_id = attrs["from_account_id"]
        to_account_id = attrs["to_account_id"]
        amount = attrs["amount"]
        user = self.context["request"].user

        if from_account_id == to_account_id:
            raise serializers.ValidationError("Le compte source et le compte destination doivent être différents.")

        try:
            from_account = Account.objects.get(id=from_account_id, user=user)
        except Account.DoesNotExist:
            raise serializers.ValidationError({"from_account_id": "Compte source introuvable ou non autorisé."})

        try:
            to_account = Account.objects.get(id=to_account_id, user=user)
        except Account.DoesNotExist:
            raise serializers.ValidationError({"to_account_id": "Compte destination introuvable ou non autorisé."})

        if from_account.current_balance < amount:
            raise serializers.ValidationError(
                {"amount": f"Solde insuffisant sur le compte source (solde actuel : {from_account.current_balance})."}
            )

        attrs["_from_account"] = from_account
        attrs["_to_account"] = to_account
        return attrs


class MobileMoneyWalletSerializer(serializers.ModelSerializer):
    """
    Vue (liste) des wallets mobile money d'un marchand.
    Le solde est porté par l'`Account` lié au wallet.
    """

    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_balance = serializers.DecimalField(source="account.current_balance", max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = MobileMoneyWallet
        fields = (
            "id",
            "provider",
            "phone_number",
            "account_id",
            "account_balance",
            "created_at",
            "updated_at",
        )


class MobileMoneyWalletCreateSerializer(serializers.Serializer):
    """Création d'un wallet mobile money (provider + phone_number)."""

    provider = serializers.CharField(max_length=30)
    phone_number = serializers.CharField(max_length=30)

    def validate_provider(self, value: str) -> str:
        return value.strip().upper()

    def validate_phone_number(self, value: str) -> str:
        # MVP: on nettoie uniquement les espaces; la normalisation “numéro” complète pourra suivre.
        return value.strip()

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        # MVP: wallet uniquement pour les professionnels.
        if not hasattr(user, "profile") or user.profile.user_type != UserProfile.USER_TYPE_PROFESSIONAL:
            raise serializers.ValidationError("Réservé aux comptes professionnels.")

        provider = validated_data["provider"]
        phone_number = validated_data["phone_number"]

        existing = MobileMoneyWallet.objects.filter(user=user, provider=provider, phone_number=phone_number).first()
        if existing:
            return existing

        # Le solde du wallet est porté par un `Account` distinct (account_type=mobile_money).
        account = Account.objects.create(
            user=user,
            name=f"Mobile Money {provider} - {phone_number}",
            account_type="mobile_money",
            initial_balance=Decimal("0"),
            current_balance=Decimal("0"),
        )
        wallet = MobileMoneyWallet.objects.create(
            user=user,
            provider=provider,
            phone_number=phone_number,
            account=account,
        )
        return wallet


class AccountBulkSyncRequestSerializer(serializers.Serializer):
    accounts = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=200)


class AccountBulkSyncResultItemSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["created", "updated", "error", "conflict"])
    id = serializers.IntegerField(required=False, allow_null=True)
    client_id = serializers.CharField(required=False, allow_blank=True)
    local_id = serializers.CharField(required=False, allow_blank=True)
    errors = serializers.DictField(required=False)
    account = AccountSerializer(required=False)
    server_account = AccountSerializer(required=False)


class AccountBulkSyncSummarySerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    error = serializers.IntegerField()
    conflict = serializers.IntegerField()


class AccountBulkSyncResponseSerializer(serializers.Serializer):
    results = AccountBulkSyncResultItemSerializer(many=True)
    summary = AccountBulkSyncSummarySerializer()
