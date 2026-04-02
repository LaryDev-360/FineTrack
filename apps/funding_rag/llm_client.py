import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


class LLMClientError(Exception):
    """Raised when LLM provider call fails."""


@dataclass
class LLMAnswer:
    answer: str
    citations: list[dict]
    limits: list[str]
    confidence: float
    model_used: str
    prompt_tokens: int
    completion_tokens: int


def _extract_json_object(text: str) -> dict:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = payload.strip("`")
        payload = payload.replace("json", "", 1).strip()
    start = payload.find("{")
    end = payload.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM output is not JSON.")
    return json.loads(payload[start : end + 1])


def _build_system_prompt(language: str) -> str:
    return (
        "Tu es un assistant de financement pour MPME. "
        "Reponds uniquement depuis le contexte fourni. "
        "Si le contexte est insuffisant, dis-le explicitement. "
        f"Reponds en langue cible '{language}'. "
        "Retourne strictement un JSON avec les cles: "
        "answer (string), citations (array of {chunk_id, document_id}), limits (array of string), confidence (number 0..1)."
    )


def _build_user_prompt(question: str, context_chunks: list[dict], language: str) -> str:
    context_lines = []
    for item in context_chunks:
        context_lines.append(
            f"[chunk_id={item['chunk_id']}|document_id={item['document_id']}] "
            f"title={item['document_title']} ; excerpt={item['excerpt']}"
        )
    context_blob = "\n".join(context_lines)
    return (
        f"Langue cible: {language}\n"
        f"Question: {question}\n"
        "Contexte:\n"
        f"{context_blob}\n\n"
        "Important: n'utilise que le contexte. Si insuffisant, indique des limites."
    )


def generate_answer_with_openrouter(*, question: str, context_chunks: list[dict], language: str) -> LLMAnswer:
    api_key = getattr(settings, "OPENROUTER_API_KEY", "")
    model = getattr(settings, "RAG_LLM_MODEL", "openai/gpt-4o-mini")
    if not api_key:
        raise LLMClientError("OPENROUTER_API_KEY manquant.")

    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _build_system_prompt(language)},
            {"role": "user", "content": _build_user_prompt(question, context_chunks, language)},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url=getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    timeout = max(5, int(getattr(settings, "RAG_LLM_TIMEOUT_SECONDS", 20)))
    retries = max(0, int(getattr(settings, "RAG_LLM_MAX_RETRIES", 2)))
    backoff = max(0.1, float(getattr(settings, "RAG_LLM_RETRY_BACKOFF_SECONDS", 1.0)))

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            choices = payload.get("choices") or []
            if not choices:
                raise LLMClientError("Aucune reponse du provider.")
            content = ((choices[0] or {}).get("message") or {}).get("content") or ""
            parsed = _extract_json_object(content)
            usage = payload.get("usage") or {}
            return LLMAnswer(
                answer=str(parsed.get("answer") or "").strip(),
                citations=list(parsed.get("citations") or []),
                limits=[str(item) for item in (parsed.get("limits") or [])],
                confidence=float(parsed.get("confidence") or 0.0),
                model_used=str(payload.get("model") or model),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, LLMClientError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (2**attempt))
                continue
            break

    raise LLMClientError(str(last_error) if last_error else "Erreur inconnue provider.")
