from rest_framework import serializers

from apps.categories.models import Category

from .models import Budget

BUDGET_BULK_PAYLOAD_FIELDS = frozenset(
    {"category", "amount", "period_start", "period_end", "is_global"}
)


class BudgetSerializer(serializers.ModelSerializer):
    """CRUD Budget : global (`is_global` + sans catégorie) ou lié à une catégorie."""

    class Meta:
        model = Budget
        fields = (
            "id",
            "category",
            "amount",
            "period_start",
            "period_end",
            "is_global",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["category"].queryset = Category.objects.filter(user=request.user)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant du budget doit être strictement positif.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        inst = self.instance

        period_start = attrs.get("period_start", inst.period_start if inst else None)
        period_end = attrs.get("period_end", inst.period_end if inst else None)
        if period_start and period_end and period_start > period_end:
            raise serializers.ValidationError(
                {"period_end": "La fin de période doit être postérieure ou égale au début (même jour autorisé)."}
            )

        is_global = attrs.get("is_global", inst.is_global if inst else False)
        category = attrs.get("category", inst.category if inst else None)

        if is_global:
            if category is not None:
                raise serializers.ValidationError(
                    {"category": "Un budget global ne doit pas avoir de catégorie."}
                )
        else:
            if category is None:
                raise serializers.ValidationError(
                    {"category": "Une catégorie est requise pour un budget non global."}
                )
            if category.user_id != user.id:
                raise serializers.ValidationError({"category": "Catégorie introuvable ou non autorisée."})

        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class BudgetBulkSyncRequestSerializer(serializers.Serializer):
    budgets = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=200)


class BudgetBulkSyncResultItemSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["created", "updated", "error", "conflict"])
    id = serializers.IntegerField(required=False, allow_null=True)
    client_id = serializers.CharField(required=False, allow_blank=True)
    local_id = serializers.CharField(required=False, allow_blank=True)
    errors = serializers.DictField(required=False)
    budget = BudgetSerializer(required=False)
    server_budget = BudgetSerializer(required=False)


class BudgetBulkSyncSummarySerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    error = serializers.IntegerField()
    conflict = serializers.IntegerField()


class BudgetBulkSyncResponseSerializer(serializers.Serializer):
    results = BudgetBulkSyncResultItemSerializer(many=True)
    summary = BudgetBulkSyncSummarySerializer()
