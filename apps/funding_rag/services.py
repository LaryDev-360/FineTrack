import hashlib
import math
import re
import time
from collections.abc import Iterable

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from .llm_client import LLMClientError, generate_answer_with_openrouter
from .models import FundingChunk, FundingDocument, IngestionJob, RagQueryLog


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    chunk_size = chunk_size or getattr(settings, "RAG_CHUNK_SIZE", 800)
    overlap = overlap if overlap is not None else getattr(settings, "RAG_CHUNK_OVERLAP", 120)
    overlap = max(0, min(overlap, chunk_size // 2))

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _hash_to_unit_interval(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    value = int(digest, 16) / 0xFFFFFFFF
    return (value * 2.0) - 1.0


def embed_text(text: str) -> list[float]:
    dimensions = int(getattr(settings, "RAG_EMBEDDING_DIM", 128))
    normalized = _normalize_text(text).lower()
    vector = [_hash_to_unit_interval(f"{normalized}:{idx}") for idx in range(dimensions)]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _to_pgvector_literal(vector: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in vector) + "]"


def resolve_query_language(
    question: str,
    user_profile_language: str = "",
    preferred_language: str = "",
) -> tuple[str, str]:
    supported = {item.lower() for item in getattr(settings, "RAG_SUPPORTED_LANGUAGES", ["fr", "en"])}
    preferred = (preferred_language or "").strip().lower()
    text = _normalize_text(question).lower()
    if not text:
        if preferred and preferred in supported:
            return preferred, "preferred_language_empty_question"
        if user_profile_language and user_profile_language.lower() in supported:
            return user_profile_language.lower(), "profile_fallback_empty_question"
        return "fr", "default_fallback_empty_question"

    english_markers = {
        "the",
        "what",
        "where",
        "loan",
        "loans",
        "funding",
        "business",
        "eligible",
        "requirements",
        "for",
        "small",
        "company",
    }
    french_markers = {
        "quel",
        "quels",
        "quelle",
        "quelles",
        "financement",
        "financements",
        "credit",
        "credits",
        "subvention",
        "subventions",
        "entreprise",
        "entreprises",
        "eligibilite",
        "pme",
        "benin",
    }
    yoruba_markers = {"owo", "kini", "ile", "ise", "awon", "owo-owo"}
    fon_markers = {"gbeta", "xo", "nu", "kpin", "doton", "wema"}

    tokens = {tok for tok in re.split(r"\W+", text) if tok}
    score_yo = len(tokens & yoruba_markers)
    score_fon = len(tokens & fon_markers)
    score_en = len(tokens & english_markers)
    score_fr = len(tokens & french_markers)

    if score_yo > 0 and "yo" in supported and score_yo >= max(score_fon, score_en, score_fr):
        return "yo", "detected_question_markers"
    if score_fon > 0 and "fon" in supported and score_fon >= max(score_yo, score_en, score_fr):
        return "fon", "detected_question_markers"
    if score_fr > 0 and "fr" in supported and score_fr >= max(score_en, score_yo, score_fon):
        return "fr", "detected_question_markers"
    if score_en > 0 and "en" in supported:
        return "en", "detected_question_markers"

    if any(ch in text for ch in ("é", "è", "à", "ù", "ç")) and "fr" in supported:
        return "fr", "detected_question_accents"

    if preferred and preferred in supported:
        return preferred, "preferred_language"
    profile_lang = (user_profile_language or "").strip().lower()
    if profile_lang in supported:
        return profile_lang, "profile_fallback"
    return "fr", "default_fallback"


def ingest_documents(*, documents: list[dict], created_by=None, source_label: str = "") -> IngestionJob:
    job = IngestionJob.objects.create(
        created_by=created_by,
        source_label=source_label,
        status=IngestionJob.STATUS_RUNNING,
        started_at=timezone.now(),
    )
    total_chunks = 0

    try:
        with transaction.atomic():
            for payload in documents:
                doc = FundingDocument.objects.create(
                    title=payload["title"].strip(),
                    source_url=payload.get("source_url", ""),
                    source_type=payload.get("source_type", FundingDocument.SOURCE_TYPE_OTHER),
                    language=(payload.get("language") or "fr").strip() or "fr",
                    country=(payload.get("country") or "BJ").strip() or "BJ",
                    status=payload.get("status", FundingDocument.STATUS_PUBLISHED),
                    published_at=payload.get("published_at"),
                    raw_content=payload["content"].strip(),
                    metadata=payload.get("metadata") or {},
                )

                chunks = chunk_text(doc.raw_content)
                chunk_models = []
                for index, chunk in enumerate(chunks):
                    chunk_models.append(
                        FundingChunk(
                            document=doc,
                            chunk_index=index,
                            content=chunk,
                            embedding=embed_text(chunk),
                            metadata=doc.metadata,
                        )
                    )
                FundingChunk.objects.bulk_create(chunk_models)
                total_chunks += len(chunk_models)

        job.status = IngestionJob.STATUS_SUCCESS
        job.total_documents = len(documents)
        job.total_chunks = total_chunks
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "total_documents",
                "total_chunks",
                "finished_at",
            ]
        )
    except Exception as exc:  # pragma: no cover - defensive path
        job.status = IngestionJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        raise

    return job


def _fallback_retrieve(question: str, top_k: int, country: str = "", language: str = "") -> list[dict]:
    tokens = [token for token in re.split(r"\W+", question.lower()) if len(token) > 2][:10]
    qs = FundingChunk.objects.select_related("document").filter(
        document__status=FundingDocument.STATUS_PUBLISHED,
    )
    if country:
        qs = qs.filter(document__country__iexact=country)
    if language:
        qs = qs.filter(document__language__iexact=language)

    rows = []
    for chunk in qs[:400]:
        content = chunk.content.lower()
        score = sum(1 for token in tokens if token in content)
        if score > 0:
            rows.append({"chunk": chunk, "distance": 1.0 / (score + 1.0)})
    rows.sort(key=lambda item: item["distance"])
    return rows[:top_k]


def retrieve_chunks(question: str, top_k: int, country: str = "", language: str = "") -> list[dict]:
    if connection.vendor != "postgresql":
        return _fallback_retrieve(question, top_k=top_k, country=country, language=language)

    query_vector = embed_text(question)
    vector_literal = _to_pgvector_literal(query_vector)
    clauses = ["d.status = %s"]
    params: list[object] = [FundingDocument.STATUS_PUBLISHED]
    if country:
        clauses.append("d.country ILIKE %s")
        params.append(country)
    if language:
        clauses.append("d.language ILIKE %s")
        params.append(language)
    where_sql = " AND ".join(clauses)

    sql = f"""
        SELECT
            c.id,
            (c.embedding <=> %s::vector) AS distance
        FROM funding_rag_chunk c
        INNER JOIN funding_rag_document d ON d.id = c.document_id
        WHERE {where_sql}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    params = [vector_literal, *params, vector_literal, top_k]

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    if not rows:
        return []
    chunk_ids = [row[0] for row in rows]
    distances_by_id = {row[0]: float(row[1]) for row in rows}
    chunks = FundingChunk.objects.select_related("document").filter(id__in=chunk_ids)
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    return [
        {"chunk": chunks_by_id[chunk_id], "distance": distances_by_id[chunk_id]}
        for chunk_id in chunk_ids
        if chunk_id in chunks_by_id
    ]


def rerank_chunks(retrieved: list[dict]) -> list[dict]:
    reranked = []
    now = timezone.now().date()
    for item in retrieved:
        chunk = item["chunk"]
        distance = max(0.0, float(item["distance"]))
        similarity = max(0.0, min(1.0, 1.0 - distance))
        publication_bonus = 0.0
        if chunk.document.published_at:
            days_old = (now - chunk.document.published_at).days
            publication_bonus = max(0.0, 0.2 - min(days_old / 3650.0, 0.2))
        metadata_bonus = 0.05 if chunk.metadata else 0.0
        score = similarity + publication_bonus + metadata_bonus
        reranked.append({"chunk": chunk, "distance": distance, "score": round(score, 5)})
    reranked.sort(key=lambda item: item["score"], reverse=True)
    return reranked


def _build_citations_from_selected(selected: list[dict]) -> list[dict]:
    citations = []
    for item in selected:
        chunk = item["chunk"]
        citations.append(
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": chunk.document.title,
                "source_url": chunk.document.source_url or "",
                "score": float(item["score"]),
                "excerpt": chunk.content[:220].strip(),
            }
        )
    return citations


def _reconcile_citations(llm_citations: list[dict], selected: list[dict]) -> list[dict]:
    selected_by_chunk = {item["chunk"].id: item for item in selected}
    selected_by_doc = {}
    for item in selected:
        selected_by_doc.setdefault(item["chunk"].document_id, item)

    citations = []
    for row in llm_citations:
        chunk_id = int(row.get("chunk_id") or 0)
        document_id = int(row.get("document_id") or 0)
        item = selected_by_chunk.get(chunk_id) or selected_by_doc.get(document_id)
        if not item:
            continue
        chunk = item["chunk"]
        citations.append(
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": chunk.document.title,
                "source_url": chunk.document.source_url or "",
                "score": float(item["score"]),
                "excerpt": chunk.content[:220].strip(),
            }
        )
    return citations


def _build_local_answer(reranked_chunks: list[dict], top_k: int) -> tuple[str, list[dict], float, list[str]]:
    selected = reranked_chunks[:top_k]
    if not selected:
        return (
            "Je ne trouve pas d'information fiable dans les sources disponibles pour cette question.",
            [],
            0.0,
            ["Aucune source pertinente n'a ete retrouvee."],
        )

    citations = _build_citations_from_selected(selected)
    seen_doc_ids = set()
    key_points = []
    for citation in citations:
        doc_id = citation["document_id"]
        if doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(doc_id)
        key_points.append(f"- {citation['document_title']}: {citation['excerpt'][:180].strip()}...")

    answer = (
        "Voici les informations de financement les plus pertinentes selon vos criteres.\n"
        + "\n".join(key_points[:3])
    )
    confidence = round(sum(c["score"] for c in citations) / max(len(citations), 1), 3)
    limits = [
        "Reponse basee uniquement sur les sources indexees.",
        "Verifier les criteres d'eligibilite aupres de l'organisme financier.",
    ]
    return answer, citations, confidence, limits


def ask_funding_question(
    *,
    user,
    question: str,
    top_k: int,
    country: str = "",
    language: str = "",
    preferred_language: str = "",
) -> dict:
    start = time.perf_counter()
    normalized_question = _normalize_text(question)
    if not normalized_question:
        normalized_question = question.strip()

    user_profile_language = ""
    if hasattr(user, "profile") and getattr(user.profile, "language", ""):
        user_profile_language = user.profile.language
    if language:
        user_profile_language = language

    detected_language, language_fallback_reason = resolve_query_language(
        normalized_question,
        user_profile_language=user_profile_language,
        preferred_language=preferred_language,
    )

    # Important: ne pas forcer le filtre par langue detectee, sinon une question EN
    # peut exclure toutes les sources FR pertinentes. Le filtre langue doit rester
    # explicite (parametre `language`) ; la langue detectee sert surtout la generation.
    retrieval_language = (language or "").strip().lower()
    max_context_chunks = max(1, int(getattr(settings, "RAG_MAX_CONTEXT_CHUNKS", 6)))
    retrieved = retrieve_chunks(
        normalized_question,
        top_k=max(top_k * 2, max_context_chunks),
        country=country,
        language=retrieval_language,
    )
    # Si un filtre langue explicite est trop restrictif, fallback sans filtre langue.
    if not retrieved and retrieval_language:
        retrieved = retrieve_chunks(
            normalized_question,
            top_k=max(top_k * 2, max_context_chunks),
            country=country,
            language="",
        )
    reranked = rerank_chunks(retrieved)

    min_relevance = float(getattr(settings, "RAG_MIN_RELEVANCE_SCORE", 0.25))
    selected = [item for item in reranked if float(item["score"]) >= min_relevance][:max_context_chunks]
    if not selected:
        selected = reranked[:max_context_chunks]

    model_used = "rag-fallback-local"
    provider = "local-fallback"
    prompt_tokens = 0
    completion_tokens = 0
    if not selected:
        answer, citations, confidence, limits = _build_local_answer([], top_k=top_k)
        limits.append("Contexte insuffisant pour generation LLM.")
    else:
        context_chunks = _build_citations_from_selected(selected)
        try:
            llm = generate_answer_with_openrouter(
                question=normalized_question,
                context_chunks=context_chunks,
                language=detected_language,
            )
            citations = _reconcile_citations(llm.citations, selected)
            if not citations:
                citations = context_chunks[:top_k]
            answer = llm.answer or "Je n'ai pas assez d'informations pour repondre de maniere fiable."
            confidence = float(llm.confidence or 0.0)
            limits = llm.limits or [
                "Verifier les criteres d'eligibilite aupres de l'organisme financier.",
            ]
            model_used = llm.model_used
            provider = "openrouter"
            prompt_tokens = llm.prompt_tokens
            completion_tokens = llm.completion_tokens
        except LLMClientError:
            answer, citations, confidence, limits = _build_local_answer(selected, top_k=top_k)
            limits.append("Generation LLM indisponible: fallback local active.")
            model_used = "rag-fallback-local"
            provider = "local-fallback"

    latency_ms = int((time.perf_counter() - start) * 1000)
    estimated_cost = 0
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens > 0:
        estimated_cost = round(total_tokens * 0.0000005, 6)

    RagQueryLog.objects.create(
        user=user,
        question=question,
        normalized_question=normalized_question,
        response_text=answer,
        selected_chunks=[
            {"chunk_id": citation["chunk_id"], "score": citation["score"]} for citation in citations
        ],
        provider=provider,
        model_used=model_used,
        detected_language=detected_language,
        language_fallback_reason=language_fallback_reason,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost,
    )

    return {
        "answer": answer,
        "confidence": confidence,
        "citations": citations,
        "limits": limits,
        "detected_language": detected_language,
        "model_used": model_used,
        "fallback_reason": language_fallback_reason,
        "latency_ms": latency_ms,
    }


def list_sources_queryset():
    return FundingDocument.objects.annotate(chunk_count=Count("chunks")).order_by("-updated_at")


def reindex_documents(*, document_id: int | None = None) -> dict:
    qs = FundingDocument.objects.all()
    if document_id:
        qs = qs.filter(id=document_id)
    documents = list(qs)
    if not documents:
        return {"documents": 0, "chunks": 0}

    total_chunks = 0
    with transaction.atomic():
        for document in documents:
            FundingChunk.objects.filter(document=document).delete()
            chunks = chunk_text(document.raw_content)
            chunk_models = [
                FundingChunk(
                    document=document,
                    chunk_index=index,
                    content=chunk,
                    embedding=embed_text(chunk),
                    metadata=document.metadata,
                )
                for index, chunk in enumerate(chunks)
            ]
            FundingChunk.objects.bulk_create(chunk_models)
            total_chunks += len(chunk_models)
    return {"documents": len(documents), "chunks": total_chunks}
