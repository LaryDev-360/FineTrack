from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class FundingDocument(models.Model):
    SOURCE_TYPE_GRANT = "grant"
    SOURCE_TYPE_LOAN = "loan"
    SOURCE_TYPE_PROGRAM = "program"
    SOURCE_TYPE_OTHER = "other"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_GRANT, "Subvention"),
        (SOURCE_TYPE_LOAN, "Pret"),
        (SOURCE_TYPE_PROGRAM, "Programme"),
        (SOURCE_TYPE_OTHER, "Autre"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PUBLISHED, "Publie"),
        (STATUS_ARCHIVED, "Archive"),
    ]

    title = models.CharField(max_length=255)
    source_url = models.URLField(blank=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default=SOURCE_TYPE_OTHER)
    language = models.CharField(max_length=8, default="fr", db_index=True)
    country = models.CharField(max_length=50, default="BJ", db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateField(null=True, blank=True, db_index=True)
    raw_content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "funding_rag_document"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class FundingChunk(models.Model):
    document = models.ForeignKey(
        FundingDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=getattr(settings, "RAG_EMBEDDING_DIM", 128))
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "funding_rag_chunk"
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "chunk_index"], name="uniq_funding_chunk_doc_index"),
        ]

    def __str__(self):
        return f"{self.document_id}:{self.chunk_index}"


class IngestionJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="funding_ingestion_jobs",
    )
    source_label = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    total_documents = models.PositiveIntegerField(default=0)
    total_chunks = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "funding_rag_ingestion_job"
        ordering = ["-created_at"]

    def __str__(self):
        return f"IngestionJob {self.id} ({self.status})"


class RagQueryLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="funding_rag_queries",
    )
    question = models.TextField()
    normalized_question = models.TextField(blank=True)
    response_text = models.TextField(blank=True)
    selected_chunks = models.JSONField(default=list, blank=True)
    provider = models.CharField(max_length=50, default="local-hash")
    model_used = models.CharField(max_length=100, blank=True)
    detected_language = models.CharField(max_length=8, blank=True)
    language_fallback_reason = models.CharField(max_length=120, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "funding_rag_query_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"RAG query {self.id}"
