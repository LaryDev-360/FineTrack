from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttles import FundingIngestThrottle, FundingLLMThrottle, FundingQueryThrottle

from .serializers import (
    AskRequestSerializer,
    AskResponseSerializer,
    FundingSourceSerializer,
    IngestRequestSerializer,
    ReindexRequestSerializer,
)
from .services import ask_funding_question, ingest_documents, list_sources_queryset, reindex_documents


@extend_schema(
    tags=["Funding RAG"],
    summary="Question financement (RAG)",
    request=AskRequestSerializer,
    responses={200: AskResponseSerializer},
)
class FundingAskView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (FundingQueryThrottle, FundingLLMThrottle)

    def post(self, request):
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        result = ask_funding_question(
            user=request.user,
            question=payload["question"],
            top_k=payload["top_k"],
            country=(payload.get("country") or "").strip(),
            language=(payload.get("language") or "").strip(),
            preferred_language=(payload.get("preferred_language") or "").strip(),
        )
        return Response(
            {
                "answer": result["answer"],
                "confidence": result["confidence"],
                "citations": result["citations"],
                "limits": result["limits"],
                "detected_language": result["detected_language"],
                "model_used": result["model_used"],
                "fallback_reason": result["fallback_reason"],
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Funding RAG"],
    summary="Ingestion d'un lot de sources de financement",
    request=IngestRequestSerializer,
)
class FundingIngestView(APIView):
    permission_classes = (IsAdminUser,)
    throttle_classes = (FundingIngestThrottle,)

    def post(self, request):
        serializer = IngestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        job = ingest_documents(
            documents=payload["documents"],
            created_by=request.user,
            source_label=payload.get("source_label", ""),
        )
        return Response(
            {
                "job_id": job.id,
                "status": job.status,
                "total_documents": job.total_documents,
                "total_chunks": job.total_chunks,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Funding RAG"],
    summary="Lister les sources indexees",
    responses={200: FundingSourceSerializer(many=True)},
)
class FundingSourcesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        data = FundingSourceSerializer(list_sources_queryset(), many=True).data
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Funding RAG"],
    summary="Reindexation des embeddings",
    request=ReindexRequestSerializer,
)
class FundingReindexView(APIView):
    permission_classes = (IsAdminUser,)
    throttle_classes = (FundingIngestThrottle,)

    def post(self, request):
        serializer = ReindexRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = reindex_documents(document_id=serializer.validated_data.get("document_id"))
        return Response(result, status=status.HTTP_200_OK)
