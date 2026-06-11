"""
Tests for all 6 roadmap agents.

All external API calls (Grants.gov, USPTO, arXiv, OpenAI, FDA ESG, Resend)
are mocked — no network traffic or API keys required.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures shared across agent tests
# ─────────────────────────────────────────────────────────────────────────────

def _make_openai_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture()
def tmp_out(tmp_path):
    return str(tmp_path)


@pytest.fixture()
def sample_opportunity():
    return {
        "opportunity_id": "OPP12345",
        "title": "Longevity and Aging Biology Research",
        "agency": "NIH",
        "close_date": "2026-12-31",
        "award_ceiling": "500000",
        "url": "https://grants.gov/OPP12345",
    }


@pytest.fixture()
def sample_project():
    return {
        "title": "AI-Driven Longevity Biomarker Discovery",
        "hypothesis": "ML models can identify novel aging biomarkers",
        "approach": "CureForge knowledge graph + ML pipeline",
        "innovation": "First AI platform combining multi-omics with clinical aging data",
        "team": "Dr. A (PI), Dr. B (Co-I)",
        "preliminary_data": "10k patient cohort baseline established",
    }


@pytest.fixture()
def sample_article():
    return {
        "title": "AI-Driven Longevity Biomarker Discovery",
        "abstract": "We present a novel approach to identifying aging biomarkers.",
        "authors": [
            {"name": "Alice Smith", "affiliation": "LongevityInTime", "email": "a@lit.org"},
            {"name": "Bob Jones", "affiliation": "MIT", "email": "b@mit.edu"},
        ],
        "keywords": ["longevity", "biomarkers", "machine learning"],
        "body_sections": [
            {"heading": "Introduction", "text": "Aging is a complex process..."},
            {"heading": "Methods", "text": "We used a graph neural network..."},
            {"heading": "Results", "text": "Our model achieved 92% AUC..."},
        ],
        "acknowledgements": "Supported by LongevityInTime Foundation.",
    }


@pytest.fixture()
def sample_invention():
    return {
        "title": "AI System for Longevity Biomarker Identification",
        "problem": "No automated way to discover aging biomarkers at scale",
        "solution": "Graph neural network trained on multi-omics data",
        "technical_details": "CureForge KG with 2M nodes, GNN + contrastive learning",
        "inventors": ["Alice Smith", "Bob Jones"],
        "assignee": "LongevityInTime Inc.",
    }


@pytest.fixture()
def sample_dataset_info():
    return {
        "name": "UKBB Longevity Cohort",
        "description": "UK Biobank subset with aging phenotypes",
        "variables": "age, telomere_length, grip_strength, cognitive_score",
        "format": "CSV",
        "record_count": "50000",
        "time_period": "2006–2020",
        "sensitivity_level": "Sensitive",
        "research_purpose": "Develop ML models to predict healthy lifespan",
    }


@pytest.fixture()
def sample_requester():
    return {
        "institution": "LongevityInTime Inc.",
        "pi_name": "Dr. Alice Smith",
        "pi_title": "Chief Scientific Officer",
        "pi_email": "alice@longevityintime.org",
        "address": "123 Research Ave, Wilmington, DE 19801",
        "irb_number": "IRB-2026-001",
    }


@pytest.fixture()
def sample_provider():
    return {
        "organization": "UK Biobank",
        "contact_name": "Dr. Data Custodian",
        "contact_email": "data@ukbiobank.ac.uk",
        "address": "Stockport, UK",
    }


@pytest.fixture()
def sample_study_info(tmp_out):
    return {
        "application_type": "IND",
        "application_number": "IND-123456",
        "sponsor_name": "LongevityInTime Inc.",
        "drug_name": "LIT-001",
        "sequence_number": "0000",
        "study_title": "Phase 1 Study of LIT-001 in Healthy Aging Adults",
        "indication": "Healthy aging",
        "documents": [
            {"module": "1", "section": "1.2", "title": "Cover Letter", "file_path": "/nonexistent/cover.pdf"},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Grant Agent
# ─────────────────────────────────────────────────────────────────────────────

class TestGrantAgent:
    def test_discover_grants_returns_list(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "hits": [
                    {
                        "id": "OPP001",
                        "title": "Longevity Research Grant",
                        "agencyName": "NIH",
                        "closeDate": "2026-12-31",
                        "awardCeiling": 500000,
                        "synopsis": "Test synopsis",
                    }
                ]
            }
        }

        with patch("agents.grant_agent.post_json", return_value=mock_resp):
            from agents.grant_agent import discover_grants
            results = discover_grants("longevity aging", limit=5)

        assert len(results) == 1
        assert results[0]["opportunity_id"] == "OPP001"
        assert results[0]["agency"] == "NIH"

    def test_discover_grants_handles_api_error(self):
        import requests as _requests
        with patch("agents.grant_agent.post_json", side_effect=_requests.RequestException("timeout")):
            from agents.grant_agent import discover_grants
            results = discover_grants("test")

        assert results == []

    def test_draft_narrative_contains_key_content(self, sample_opportunity, sample_project):
        with patch("agents.grant_agent.chat_completion_text", return_value="Specific Aim 1: Identify biomarkers.\nSpecific Aim 2: Validate them."):
            from agents.grant_agent import draft_narrative
            result = draft_narrative(sample_opportunity, sample_project)

        assert "Specific Aim" in result

    def test_draft_narrative_sends_opportunity_to_openai(self, sample_opportunity, sample_project):
        with patch("agents.grant_agent.chat_completion_text", return_value="narrative text") as mock_chat:
            from agents.grant_agent import draft_narrative
            draft_narrative(sample_opportunity, sample_project)

        user_prompt = mock_chat.call_args[1]["user_prompt"]
        assert sample_opportunity["title"] in user_prompt
        assert sample_project["hypothesis"] in user_prompt

    def test_validate_project_info_raises_on_missing(self, sample_opportunity):
        from agents.grant_agent import GrantValidationError, draft_narrative, validate_project_info

        bad = {"title": "only title"}
        with pytest.raises(GrantValidationError) as exc:
            validate_project_info(bad)
        assert "hypothesis" in exc.value.missing

        with pytest.raises(GrantValidationError):
            draft_narrative(sample_opportunity, bad, validate=True)

    def test_draft_narrative_workflow_returns_steps(self, sample_opportunity, sample_project):
        with patch(
            "agents.grant_agent.chat_completion_text",
            side_effect=["- outline bullet", "draft body", "1. critique item", "final narrative text"],
        ):
            from agents.grant_agent import draft_narrative_workflow
            out = draft_narrative_workflow(sample_opportunity, sample_project, include_landscape=False)

        assert out["narrative"] == "final narrative text"
        assert "critique" in out

    def test_save_application_package_writes_files(self, sample_opportunity, sample_project, tmp_out):
        from agents.grant_agent import save_application_package

        pkg = save_application_package(
            "Final narrative.",
            sample_opportunity,
            sample_project,
            output_dir=tmp_out,
            workflow_artifacts={"outline": "o", "draft": "d", "critique": "c", "narrative": "Final narrative."},
        )
        assert pkg.is_dir()
        assert (pkg / "narrative.md").read_text()
        assert (pkg / "metadata.json").read_text()
        assert (pkg / "checklist.md").read_text()
        assert (pkg / "artifact_outline.md").read_text() == "o"

    def test_save_application_creates_file(self, sample_opportunity, tmp_out):
        from agents.grant_agent import save_application
        path = save_application("## Specific Aims\n\nAim 1: ...", sample_opportunity, output_dir=tmp_out)

        assert path.exists()
        content = path.read_text()
        assert sample_opportunity["title"] in content

    def test_search_nih_reporter_returns_list(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "project_num": "R01AG123456",
                    "project_title": "Aging Biomarker Study",
                    "fiscal_year": 2025,
                    "principal_investigators": [{"full_name": "Dr. Alice Smith"}],
                    "total_cost": 450000,
                    "abstract_text": "We study aging biomarkers...",
                }
            ]
        }

        with patch("agents.grant_agent.post_json", return_value=mock_resp):
            from agents.grant_agent import search_nih_reporter
            results = search_nih_reporter("aging biomarkers")

        assert len(results) == 1
        assert results[0]["project_num"] == "R01AG123456"


# ─────────────────────────────────────────────────────────────────────────────
# Preprint Agent
# ─────────────────────────────────────────────────────────────────────────────

class TestPreprintAgent:
    def test_search_arxiv_returns_papers(self):
        pytest.importorskip("arxiv", reason="arxiv not installed")
        mock_paper = MagicMock()
        mock_paper.entry_id = "http://arxiv.org/abs/2501.00001v1"
        mock_paper.title = "Longevity Biomarkers via ML"
        mock_paper.authors = [MagicMock(name="Alice Smith")]
        mock_paper.published.isoformat.return_value = "2025-01-01T00:00:00"
        mock_paper.summary = "We study aging."
        mock_paper.pdf_url = "http://arxiv.org/pdf/2501.00001"
        mock_paper.categories = ["q-bio.GN"]

        with patch("agents.preprint_agent.arxiv.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.results.return_value = iter([mock_paper])
            mock_client_cls.return_value = mock_client

            from agents.preprint_agent import search_arxiv
            results = search_arxiv("longevity biomarkers", max_results=3)

        assert len(results) == 1
        assert results[0]["title"] == "Longevity Biomarkers via ML"

    def test_search_arxiv_with_category_filter(self):
        pytest.importorskip("arxiv", reason="arxiv not installed")
        with patch("agents.preprint_agent.arxiv.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.results.return_value = iter([])
            mock_client_cls.return_value = mock_client
            mock_search_cls = MagicMock()

            with patch("agents.preprint_agent.arxiv.Search", return_value=mock_search_cls) as mock_search:
                from agents.preprint_agent import search_arxiv
                search_arxiv("longevity", category="q-bio.GN")

            query_arg = mock_search.call_args[1]["query"]
            assert "cat:q-bio.GN" in query_arg

    def test_prepare_biorxiv_creates_files(self, tmp_out):
        article = {
            "title": "Test Paper",
            "abstract": "We study aging.",
            "authors": ["Alice Smith", "Bob Jones"],
            "category": "Genomics",
            "keywords": ["longevity", "aging"],
        }

        from agents.preprint_agent import prepare_biorxiv_submission
        out_dir = prepare_biorxiv_submission(article, output_dir=tmp_out)

        assert (out_dir / "biorxiv_metadata.md").exists()
        assert (out_dir / "biorxiv_checklist.md").exists()
        content = (out_dir / "biorxiv_metadata.md").read_text()
        assert article["title"] in content

    def test_submit_to_arxiv_raises_without_credentials(self, tmp_path):
        tar_path = tmp_path / "paper.tar.gz"
        tar_path.write_bytes(b"fake tar content")

        with patch("agents.preprint_agent.settings.arxiv_username", ""):
            from agents.preprint_agent import submit_to_arxiv
            with pytest.raises(ValueError, match="credentials required"):
                submit_to_arxiv(
                    {"title": "T", "summary": "S", "authors": ["A"], "category": "q-bio"},
                    str(tar_path),
                    username="",
                    password="",
                )

    def test_submit_to_arxiv_raises_for_missing_file(self):
        from agents.preprint_agent import submit_to_arxiv
        with pytest.raises(FileNotFoundError):
            submit_to_arxiv(
                {"title": "T", "summary": "S", "authors": ["A"], "category": "q-bio"},
                "/no/such/file.tar.gz",
                username="user",
                password="pass",
            )

    def test_submit_to_arxiv_posts_to_sword_endpoint(self, tmp_path):
        tar = tmp_path / "paper.tar.gz"
        tar.write_bytes(b"\x1f\x8b\x08content")  # fake gzip bytes

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.headers = {"Location": "http://arxiv.org/submit/12345"}
        mock_resp.text = ""

        with patch("agents.preprint_agent.requests.post", return_value=mock_resp) as mock_post:
            from agents.preprint_agent import submit_to_arxiv
            result = submit_to_arxiv(
                {"title": "T", "summary": "S", "authors": ["Alice"], "category": "q-bio.GN"},
                str(tar),
                username="user",
                password="pass",
            )

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "arxiv.org" in call_url
        assert result == "http://arxiv.org/submit/12345"


# ─────────────────────────────────────────────────────────────────────────────
# Journal Agent
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalAgent:
    def test_build_jats_xml_is_valid_xml(self, sample_article):
        lxml_etree = pytest.importorskip("lxml.etree", reason="lxml not installed")
        from agents.journal_agent import build_jats_xml
        xml_str = build_jats_xml({**sample_article, "journal": "Nature Aging"})
        root = lxml_etree.fromstring(xml_str.encode("utf-8"))
        assert root is not None

    def test_build_jats_xml_contains_title(self, sample_article):
        pytest.importorskip("lxml", reason="lxml not installed")
        from agents.journal_agent import build_jats_xml
        xml_str = build_jats_xml({**sample_article, "journal": "Nature Aging"})
        assert sample_article["title"] in xml_str

    def test_build_jats_xml_contains_all_authors(self, sample_article):
        pytest.importorskip("lxml", reason="lxml not installed")
        from agents.journal_agent import build_jats_xml
        xml_str = build_jats_xml({**sample_article, "journal": "Cell"})
        assert "Smith" in xml_str
        assert "Jones" in xml_str

    def test_build_jats_xml_contains_abstract(self, sample_article):
        pytest.importorskip("lxml", reason="lxml not installed")
        from agents.journal_agent import build_jats_xml
        xml_str = build_jats_xml({**sample_article, "journal": "eLife"})
        assert sample_article["abstract"] in xml_str

    def test_draft_cover_letter_uses_journal_name(self, sample_article):
        mock_response = _make_openai_response("Dear Editor of Nature Aging, we submit our manuscript...")

        with patch("agents.journal_agent._get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            from agents.journal_agent import draft_cover_letter
            result = draft_cover_letter(sample_article, "Nature Aging")

        assert len(result) > 0

    def test_draft_cover_letter_passes_journal_to_openai(self, sample_article):
        mock_response = _make_openai_response("cover letter text")

        with patch("agents.journal_agent._get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            from agents.journal_agent import draft_cover_letter
            draft_cover_letter(sample_article, "Cell Systems")
            mock_create = mock_client.return_value.chat.completions.create

        user_msg = next(m for m in mock_create.call_args[1]["messages"] if m["role"] == "user")
        assert "Cell Systems" in user_msg["content"]

    def test_export_submission_package_creates_all_files(self, sample_article, tmp_out):
        pytest.importorskip("lxml", reason="lxml not installed")
        mock_response = _make_openai_response("cover letter content")

        with patch("agents.journal_agent._get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            from agents.journal_agent import export_submission_package
            out = export_submission_package(sample_article, "Nature Aging", output_dir=tmp_out)

        assert (out / "manuscript.jats.xml").exists()
        assert (out / "cover_letter.txt").exists()
        assert (out / "checklist.md").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Patent Agent
# ─────────────────────────────────────────────────────────────────────────────

class TestPatentAgent:
    def test_search_prior_art_returns_list(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "PatentNumber": "US11234567",
                            "PatentTitle": "Biomarker Detection System",
                            "PatentAbstract": "A system for detecting aging biomarkers...",
                            "InventorName": ["John Doe"],
                            "AssigneeEntityName": "BioTech Corp",
                            "ApplicationDate": "2023-01-15",
                        }
                    }
                ]
            }
        }

        with patch("agents.patent_agent.requests.get", return_value=mock_resp):
            from agents.patent_agent import search_prior_art
            results = search_prior_art("longevity biomarker ML")

        assert len(results) == 1
        assert results[0]["patent_number"] == "US11234567"

    def test_search_prior_art_handles_api_error(self):
        import requests as _requests
        with patch("agents.patent_agent.requests.get", side_effect=_requests.RequestException("timeout")):
            from agents.patent_agent import search_prior_art
            results = search_prior_art("test keywords")

        assert results == []

    def test_draft_provisional_contains_claims(self, sample_invention):
        mock_response = _make_openai_response(
            "TITLE: AI System\n\nCLAIMS\n1. A method comprising...\n2. The method of claim 1..."
        )

        with patch("agents.patent_agent._get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            from agents.patent_agent import draft_provisional
            result = draft_provisional(sample_invention)

        assert "CLAIMS" in result or "claim" in result.lower()

    def test_draft_provisional_uses_low_temperature(self, sample_invention):
        mock_response = _make_openai_response("patent text")

        with patch("agents.patent_agent._get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            from agents.patent_agent import draft_provisional
            draft_provisional(sample_invention)
            mock_create = mock_client.return_value.chat.completions.create

        assert mock_create.call_args[1]["temperature"] == 0.2

    def test_draft_provisional_includes_prior_art_in_prompt(self, sample_invention):
        mock_response = _make_openai_response("patent text")
        prior_art = [{"patent_number": "US99999", "title": "Old System", "filing_date": "2020-01-01"}]

        with patch("agents.patent_agent._get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            from agents.patent_agent import draft_provisional
            draft_provisional(sample_invention, prior_art=prior_art)
            mock_create = mock_client.return_value.chat.completions.create

        user_msg = next(m for m in mock_create.call_args[1]["messages"] if m["role"] == "user")
        assert "US99999" in user_msg["content"]

    def test_save_provisional_creates_file(self, sample_invention, tmp_out):
        from agents.patent_agent import save_provisional
        path = save_provisional("CLAIMS\n1. A method...", sample_invention, output_dir=tmp_out)

        assert path.exists()
        content = path.read_text()
        assert "DRAFT" in content
        assert "patentcenter.uspto.gov" in content


# ─────────────────────────────────────────────────────────────────────────────
# DUA Agent
# ─────────────────────────────────────────────────────────────────────────────

class TestDuaAgent:
    def test_draft_dua_returns_text(self, sample_dataset_info, sample_requester, sample_provider):
        mock_response = _make_openai_response(
            "DATA USE AGREEMENT\n\nPARTIES\nProvider: UK Biobank\nRecipient: LongevityInTime..."
        )

        with patch("agents.dua_agent._client.chat.completions.create", return_value=mock_response):
            from agents.dua_agent import draft_dua
            result = draft_dua(sample_dataset_info, sample_requester, sample_provider)

        assert len(result) > 0

    def test_draft_dua_includes_dataset_in_prompt(self, sample_dataset_info, sample_requester, sample_provider):
        mock_response = _make_openai_response("DUA text")

        with patch("agents.dua_agent._client.chat.completions.create", return_value=mock_response) as mock_create:
            from agents.dua_agent import draft_dua
            draft_dua(sample_dataset_info, sample_requester, sample_provider)

        user_msg = next(m for m in mock_create.call_args[1]["messages"] if m["role"] == "user")
        assert sample_dataset_info["name"] in user_msg["content"]
        assert sample_requester["institution"] in user_msg["content"]

    def test_draft_request_letter_returns_text(self, sample_dataset_info, sample_requester, sample_provider):
        mock_response = _make_openai_response("Dear Dr. Custodian, I am writing to request access...")

        with patch("agents.dua_agent._client.chat.completions.create", return_value=mock_response):
            from agents.dua_agent import draft_request_letter
            result = draft_request_letter(sample_dataset_info, sample_requester, sample_provider)

        assert len(result) > 0

    def test_build_data_descriptor_structure(self, sample_dataset_info):
        from agents.dua_agent import build_data_descriptor
        descriptor = build_data_descriptor(
            sample_dataset_info,
            schema=[
                {"name": "age", "type": "integer", "description": "Age in years"},
                {"name": "telomere_length", "type": "number", "description": "Telomere length (kb)"},
            ],
        )

        assert descriptor["name"] == "ukbb-longevity-cohort"
        assert len(descriptor["resources"]) == 1
        fields = descriptor["resources"][0]["schema"]["fields"]
        assert any(f["name"] == "age" for f in fields)
        assert any(f["name"] == "telomere_length" for f in fields)

    def test_build_data_descriptor_from_variables_string(self, sample_dataset_info):
        from agents.dua_agent import build_data_descriptor
        descriptor = build_data_descriptor(sample_dataset_info)

        fields = descriptor["resources"][0]["schema"]["fields"]
        field_names = [f["name"] for f in fields]
        assert "age" in field_names
        assert "telomere_length" in field_names

    def test_save_dua_package_creates_files(self, tmp_out, sample_dataset_info):
        from agents.dua_agent import save_dua_package
        descriptor = {"name": "test", "resources": []}
        out = save_dua_package(
            dua_text="DUA draft content",
            request_letter="Request letter content",
            descriptor=descriptor,
            dataset_name="Test Dataset",
            output_dir=tmp_out,
        )

        assert out.exists()
        files = list(out.iterdir())
        names = [f.name for f in files]
        assert any("dua_draft" in n for n in names)
        assert any("request_letter" in n for n in names)
        assert "datapackage.json" in names

    def test_dua_draft_contains_disclaimer(self, tmp_out, sample_dataset_info):
        from agents.dua_agent import save_dua_package
        out = save_dua_package("Draft", "Letter", {}, "My Dataset", output_dir=tmp_out)
        dua_file = next(f for f in out.iterdir() if "dua_draft" in f.name)
        assert "DRAFT" in dua_file.read_text()


# ─────────────────────────────────────────────────────────────────────────────
# FDA Agent
# ─────────────────────────────────────────────────────────────────────────────

class TestFdaAgent:
    def test_build_ectd_package_creates_structure(self, sample_study_info, tmp_out):
        pytest.importorskip("lxml", reason="lxml not installed")
        sample_study_info_copy = {**sample_study_info}

        from agents.fda_agent import build_ectd_package
        pkg_dir = build_ectd_package(sample_study_info_copy, output_dir=tmp_out)

        assert pkg_dir.exists()
        # Check module directories exist
        for mod in ["m1", "m2", "m3", "m4", "m5"]:
            assert (pkg_dir / mod).exists()

    def test_build_ectd_package_creates_index_xml(self, sample_study_info, tmp_out):
        lxml_etree = pytest.importorskip("lxml.etree", reason="lxml not installed")
        from agents.fda_agent import build_ectd_package
        pkg_dir = build_ectd_package(sample_study_info, output_dir=tmp_out)

        assert (pkg_dir / "index.xml").exists()
        content = (pkg_dir / "index.xml").read_text()
        assert sample_study_info["sponsor_name"] in content
        assert sample_study_info["drug_name"] in content
        lxml_etree.fromstring(content.encode("utf-8"))

    def test_build_ectd_blocked_when_manifest_fails(self, sample_study_info, tmp_out):
        pytest.importorskip("lxml", reason="lxml not installed")
        from agents.fda_agent import build_ectd_package

        bad_manifest = {
            "phase": "Phase 1",
            "identifiers": [{"type": "NCT", "value": "NCT05606341", "provenance": "placeholder"}],
            "drugs": [{"id": "drug_1", "is_placeholder": True, "mechanism": "LOXL2 inhibitor"}],
            "sections": {"2.2": {"status": "present"}},
            "statistics": [],
            "hallmark_targets": [],
            "aging_coverage_score": 0.0,
            "selected_hypothesis": {"acs": 0.0},
            "alternatives": [],
            "signatories": [],
        }
        prose = "Trial NCT05606341 had 212 participants for drug_1."
        with pytest.raises(ValueError, match="validation gate failed"):
            build_ectd_package(
                sample_study_info,
                output_dir=tmp_out,
                manifest=bad_manifest,
                prose=prose,
            )

    def test_build_ectd_package_creates_md5_index(self, sample_study_info, tmp_out):
        pytest.importorskip("lxml", reason="lxml not installed")
        from agents.fda_agent import build_ectd_package
        pkg_dir = build_ectd_package(sample_study_info, output_dir=tmp_out)

        assert (pkg_dir / "index-md5.xml").exists()
        content = (pkg_dir / "index-md5.xml").read_text()
        assert "md5" in content

    def test_zip_ectd_package_creates_zip(self, sample_study_info, tmp_out):
        pytest.importorskip("lxml", reason="lxml not installed")
        from agents.fda_agent import build_ectd_package, zip_ectd_package
        pkg_dir = build_ectd_package(sample_study_info, output_dir=tmp_out)
        zip_path = zip_ectd_package(pkg_dir)

        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_get_esg_token_raises_without_credentials(self):
        with patch("agents.fda_agent.settings.fda_client_id", ""), \
             patch("agents.fda_agent.settings.fda_client_secret", ""):
            from agents.fda_agent import get_esg_token
            with pytest.raises(ValueError, match="credentials required"):
                get_esg_token(client_id="", client_secret="")

    def test_get_esg_token_returns_token(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "test_token_abc"}

        with patch("agents.fda_agent.requests.post", return_value=mock_resp):
            from agents.fda_agent import get_esg_token
            token = get_esg_token(client_id="cid", client_secret="csec")

        assert token == "test_token_abc"

    def test_get_esg_token_raises_on_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("agents.fda_agent.requests.post", return_value=mock_resp):
            from agents.fda_agent import get_esg_token
            with pytest.raises(RuntimeError, match="ESG token request failed"):
                get_esg_token(client_id="bad", client_secret="bad")

    def test_upload_to_esg_calls_credentials_then_s3(self, tmp_path):
        zip_file = tmp_path / "package.zip"
        zip_file.write_bytes(b"zip content")

        cred_resp = MagicMock()
        cred_resp.status_code = 200
        cred_resp.json.return_value = {
            "submissionId": "SUB-2026-001",
            "presignedUrl": "https://s3.amazonaws.com/fda-esg/upload",
            "fields": {},
        }

        upload_resp = MagicMock()
        upload_resp.status_code = 200

        with patch("agents.fda_agent.requests.post", return_value=cred_resp), \
             patch("agents.fda_agent.requests.put", return_value=upload_resp):
            from agents.fda_agent import upload_to_esg
            submission_id = upload_to_esg(zip_file, "bearer_token", "IND", "IND-123456")

        assert submission_id == "SUB-2026-001"

    def test_check_submission_status_returns_dict(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "submissionId": "SUB-2026-001",
            "status": "processing",
            "message": "Submission received",
            "timestamp": "2026-04-22T12:00:00Z",
        }

        with patch("agents.fda_agent.requests.get", return_value=mock_resp):
            from agents.fda_agent import check_submission_status
            result = check_submission_status("SUB-2026-001", "token")

        assert result["status"] == "processing"
        assert result["submissionId"] == "SUB-2026-001"
