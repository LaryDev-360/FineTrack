from django.db import transaction
from rest_framework import serializers

from apps.categories.models import Category
from apps.core.models import Account
from apps.transactions.models import Transaction

from .services import apply_transaction_effect, reverse_transaction_effect

# Champs métier uniquement (hors sync bulk)
TRANSACTION_PAYLOAD_FIELDS = {
    "transaction_type",
    "amount",
    "account",
    "category",
    "to_account",
    "date",
    "note",
    "is_synced",
}

# Identifiants côté client (non stockés en base)
# `client_updated_at` : horodatage `updated_at` connu du client au moment de l’édition (anti-conflit).
BULK_META_KEYS = frozenset({"client_id", "local_id", "client_updated_at"})


class TransactionSerializer(serializers.ModelSerializer):
    """CRUD Transaction avec mise à jour des soldes des comptes."""

    class Meta:
        model = Transaction
        fields = (
            "id",
            "user",
            "transaction_type",
            "amount",
            "account",
            "category",
            "to_account",
            "date",
            "note",
            "is_synced",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")
        extra_kwargs = {
            "note": {"max_length": 5000},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["account"].queryset = Account.objects.filter(user=request.user, is_active=True)
            self.fields["to_account"].queryset = Account.objects.filter(user=request.user, is_active=True)
            self.fields["category"].queryset = Category.objects.filter(user=request.user)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        inst = self.instance

        tx_type = attrs.get("transaction_type", inst.transaction_type if inst else None)
        account = attrs.get("account", inst.account if inst else None)
        to_acc = attrs.get("to_account", inst.to_account if inst else None)
        category = attrs.get("category", inst.category if inst else None)

        if not account:
            raise serializers.ValidationError({"account": "Ce champ est obligatoire."})

        if account.user_id != user.id:
            raise serializers.ValidationError({"account": "Compte introuvable ou non autorisé."})
        if not account.is_active:
            raise serializers.ValidationError({"account": "Ce compte n'est pas actif."})

        if tx_type == "transfer":
            if category is not None:
                raise serializers.ValidationError({"category": "Un transfert ne doit pas avoir de catégorie."})
            if not to_acc:
                raise serializers.ValidationError({"to_account": "Le compte destination est obligatoire pour un transfert."})
            if to_acc.user_id != user.id:
                raise serializers.ValidationError({"to_account": "Compte destination introuvable ou non autorisé."})
            if not to_acc.is_active:
                raise serializers.ValidationError({"to_account": "Le compte destination n'est pas actif."})
            if account.id == to_acc.id:
                raise serializers.ValidationError({"to_account": "Les comptes source et destination doivent être différents."})
            if account.currency != to_acc.currency:
                raise serializers.ValidationError({"to_account": "Les deux comptes doivent avoir la même devise."})
        else:
            if to_acc is not None:
                raise serializers.ValidationError({"to_account": "Ce champ doit être vide sauf pour un transfert."})
            if category is not None:
                if category.user_id != user.id:
                    raise serializers.ValidationError({"category": "Catégorie introuvable ou non autorisée."})
                if tx_type == "expense" and category.category_type != "expense":
                    raise serializers.ValidationError({"category": "La catégorie doit être de type dépense."})
                if tx_type == "income" and category.category_type != "income":
                    raise serializers.ValidationError({"category": "La catégorie doit être de type revenu."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        tx = Transaction.objects.create(**validated_data)
        apply_transaction_effect(tx)
        return tx

    @transaction.atomic
    def update(self, instance, validated_data):
        reverse_transaction_effect(instance)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        apply_transaction_effect(instance)
        return instance


class BulkSyncRequestSerializer(serializers.Serializer):
    transactions = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=500,
    )


class BulkSyncResultItemSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["created", "updated", "error", "conflict"])
    id = serializers.IntegerField(required=False, allow_null=True)
    client_id = serializers.CharField(required=False, allow_blank=True)
    local_id = serializers.CharField(required=False, allow_blank=True)
    errors = serializers.DictField(required=False)
    transaction = TransactionSerializer(required=False)
    server_transaction = TransactionSerializer(required=False)


class BulkSyncSummarySerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    error = serializers.IntegerField()
    conflict = serializers.IntegerField()


class BulkSyncResponseSerializer(serializers.Serializer):
    results = BulkSyncResultItemSerializer(many=True)
    summary = BulkSyncSummarySerializer()
