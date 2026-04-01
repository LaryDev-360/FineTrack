from django.contrib import admin

from .models import FundingChunk, FundingDocument, IngestionJob, RagQueryLog


@admin.register(FundingDocument)
class FundingDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "source_type", "country", "language", "status", "updated_at")
    list_filter = ("source_type", "country", "language", "status")
    search_fields = ("title", "source_url", "raw_content")


@admin.register(FundingChunk)
class FundingChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index", "created_at")
    list_filter = ("document__country", "document__language")
    search_fields = ("content",)


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = ("id", "source_label", "status", "total_documents", "total_chunks", "created_at")
    list_filter = ("status",)
    search_fields = ("source_label", "error_message")


@admin.register(RagQueryLog)
class RagQueryLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "latency_ms", "created_at")
    search_fields = ("question", "response_text")
