"""Issue-sync manifest export tests."""

from __future__ import annotations

from scripts.export_issue_sync_manifest import build_issue_sync_manifest


def test_issue_sync_manifest_tracks_repo_complete_created_issues() -> None:
    payload = build_issue_sync_manifest()

    assert payload["scope"] == "created_issues_repo_complete_evidence_catalog"
    assert len(payload["issues"]) >= 10
    assert any(item["issue"] == 17 and "7860056" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 27 and "72c4a08" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 35 and item["repo_status"] == "repo_complete" for item in payload["issues"])
    assert any(item["issue"] == 38 and "7860056" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 39 and "4b86023" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 45 and "2c2a843" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 48 and "39ac91d" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 49 and "8f454da" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 50 and "8f454da" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 51 and "09f6990" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 52 and "09f6990" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 53 and "09f6990" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 54 and "09f6990" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 55 and "09f6990" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 56 and "d627c73" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 57 and "d627c73" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 58 and "d627c73" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 59 and "8d311cb" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 60 and item["sync_action"] == "close_if_architecture_replacement_accepted" for item in payload["issues"])
    assert any(item["issue"] == 61 and "8d311cb" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 62 and "8d311cb" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 63 and "8d311cb" in item["evidence_commits"] for item in payload["issues"])
    assert any(item["issue"] == 64 and item["repo_status"] == "repo_complete" for item in payload["issues"])
    assert any(item["issue"] == 72 and item["repo_status"] == "local_preview_complete" for item in payload["issues"])
    assert any(item["issue"] == 78 and "b6f4dc7" in item["evidence_commits"] for item in payload["issues"])
    assert all(item["sync_action"] for item in payload["issues"])
    assert all(item["evidence_commits"] for item in payload["issues"])
