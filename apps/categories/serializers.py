from rest_framework import serializers

from .models import Category

CATEGORY_BULK_PAYLOAD_FIELDS = frozenset(
    {"name", "category_type", "color", "icon", "is_default"}
)


class CategorySerializer(serializers.ModelSerializer):
    """CRUD Catégories (dépenses / revenus)."""

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "category_type",
            "color",
            "icon",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "name": {"max_length": 100},
            "color": {"max_length": 7},
            "icon": {"max_length": 50},
        }


class CategoryBulkSyncRequestSerializer(serializers.Serializer):
    categories = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=300)


class CategoryBulkSyncResultItemSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["created", "updated", "error", "conflict"])
    id = serializers.IntegerField(required=False, allow_null=True)
    client_id = serializers.CharField(required=False, allow_blank=True)
    local_id = serializers.CharField(required=False, allow_blank=True)
    errors = serializers.DictField(required=False)
    category = CategorySerializer(required=False)
    server_category = CategorySerializer(required=False)


class CategoryBulkSyncSummarySerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    error = serializers.IntegerField()
    conflict = serializers.IntegerField()


class CategoryBulkSyncResponseSerializer(serializers.Serializer):
    results = CategoryBulkSyncResultItemSerializer(many=True)
    summary = CategoryBulkSyncSummarySerializer()
