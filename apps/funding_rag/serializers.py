from rest_framework import serializers

from .models import FundingDocument


class FundingDocumentInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    content = serializers.CharField()
    source_url = serializers.URLField(required=False, allow_blank=True)
    source_type = serializers.ChoiceField(
        choices=FundingDocument.SOURCE_TYPE_CHOICES,
        default=FundingDocument.SOURCE_TYPE_OTHER,
    )
    language = serializers.CharField(required=False, default="fr")
    country = serializers.CharField(required=False, default="BJ")
    published_at = serializers.DateField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)
    status = serializers.ChoiceField(
        choices=FundingDocument.STATUS_CHOICES,
        default=FundingDocument.STATUS_PUBLISHED,
    )

    def validate_content(self, value):
        content = value.strip()
        if not content:
            raise serializers.ValidationError("Le contenu du document ne peut pas etre vide.")
        return content


class IngestRequestSerializer(serializers.Serializer):
    source_label = serializers.CharField(required=False, allow_blank=True, max_length=255)
    documents = FundingDocumentInputSerializer(many=True)

    def validate_documents(self, value):
        if not value:
            raise serializers.ValidationError("Au moins un document est requis.")
        return value


class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1200)
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=10, default=5)
    country = serializers.CharField(required=False, allow_blank=True)
    language = serializers.CharField(required=False, allow_blank=True)

    def validate_question(self, value):
        question = value.strip()
        if not question:
            raise serializers.ValidationError("La question ne peut pas etre vide.")
        return question


class CitationSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField()
    document_id = serializers.IntegerField()
    document_title = serializers.CharField()
    source_url = serializers.CharField(allow_blank=True)
    score = serializers.FloatField()
    excerpt = serializers.CharField()


class AskResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    confidence = serializers.FloatField()
    citations = CitationSerializer(many=True)
    limits = serializers.ListField(child=serializers.CharField(), default=list)


class ReindexRequestSerializer(serializers.Serializer):
    document_id = serializers.IntegerField(required=False, min_value=1)


class FundingSourceSerializer(serializers.ModelSerializer):
    chunk_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = FundingDocument
        fields = (
            "id",
            "title",
            "source_url",
            "source_type",
            "language",
            "country",
            "status",
            "version",
            "published_at",
            "chunk_count",
            "updated_at",
        )
