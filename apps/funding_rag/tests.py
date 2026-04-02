from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import FundingChunk, FundingDocument, RagQueryLog
from .services import chunk_text, resolve_query_language

User = get_user_model()


class ChunkingTests(TestCase):
    def test_chunk_text_returns_overlap_chunks(self):
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=300, overlap=50)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(chunks[0][-50:], chunks[1][:50])


class LanguageResolutionTests(TestCase):
    def test_detects_english_marker(self):
        lang, reason = resolve_query_language("What funding options are available for my business?")
        self.assertEqual(lang, "en")
        self.assertTrue(reason.startswith("detected_"))

    def test_uses_profile_fallback(self):
        lang, reason = resolve_query_language("question neutre", user_profile_language="fr")
        self.assertEqual(lang, "fr")
        self.assertEqual(reason, "profile_fallback")

    def test_prefers_detected_language_over_preferred_language(self):
        lang, reason = resolve_query_language(
            "Quels financements existent pour une PME agroalimentaire au Benin ?",
            preferred_language="en",
        )
        self.assertEqual(lang, "fr")
        self.assertEqual(reason, "detected_question_markers")


class FundingRagApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="user@example.com",
            email="user@example.com",
            password="StrongPass123",
        )
        self.admin = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="StrongPass123",
            is_staff=True,
        )

    def test_ingest_requires_admin(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/funding/ingest/",
            {"documents": [{"title": "Doc", "content": "Texte"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_full_rag_flow_api(self):
        self.client.force_authenticate(self.admin)
        ingest_response = self.client.post(
            "/api/funding/ingest/",
            {
                "source_label": "batch-1",
                "documents": [
                    {
                        "title": "Fonds PME Bénin",
                        "content": "Le fonds PME Benin finance les entreprises de transformation agroalimentaire. Montant maximum 10 millions XOF.",
                        "source_url": "https://example.org/fonds-pme",
                        "source_type": "grant",
                        "language": "fr",
                        "country": "BJ",
                        "status": "published",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(ingest_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FundingDocument.objects.count(), 1)
        self.assertGreater(FundingChunk.objects.count(), 0)

        sources_response = self.client.get("/api/funding/sources/")
        self.assertEqual(sources_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sources_response.data), 1)

        self.client.force_authenticate(self.user)
        ask_response = self.client.post(
            "/api/funding/ask/",
            {"question": "Quel financement existe pour PME agroalimentaire au Benin ?", "top_k": 3},
            format="json",
        )
        self.assertEqual(ask_response.status_code, status.HTTP_200_OK)
        self.assertIn("answer", ask_response.data)
        self.assertIn("citations", ask_response.data)
        self.assertIn("detected_language", ask_response.data)
        self.assertIn("model_used", ask_response.data)
        self.assertIn("fallback_reason", ask_response.data)
        self.assertGreaterEqual(len(ask_response.data["citations"]), 1)
        self.assertEqual(RagQueryLog.objects.count(), 1)

    def test_ask_guardrail_when_no_document(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/funding/ask/",
            {"question": "Avez-vous des offres de microcredit ?"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["citations"]), 0)
        self.assertIn("Je ne trouve pas", response.data["answer"])
