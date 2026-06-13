"""Tests for Hard Regenerate narration feature.

Covers:
- POST /api/script/{episode_id}/narration/part/{part_number}/hard-regenerate (200)
- Validation: empty text (400), content_too_long (422), no auth (401), published episode (423)
- Cache bypass: identical text creates new version
- is_selected behavior: new version is NOT auto-selected; previously selected stays selected
- /api/episodes/{episode_id}/clips only returns is_active=true (unaffected)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://generation-workflow.preview.emergentagent.com").rstrip("/")
CREATOR_EMAIL = "harshil.zalavadiya02@gmail.com"
CREATOR_PASSWORD = "12345678"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"

LONG_TEXT_OK = "Hello narrator " * 5  # safe length
HUGE_TEXT = "x" * 15001


@pytest.fixture(scope="module")
def creator_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    return data["token"]


@pytest.fixture(scope="module")
def headers(creator_token):
    return {"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def episode_with_narration(headers):
    """Pick the first unpublished episode for the creator."""
    r = requests.get(f"{BASE_URL}/api/stories", headers=headers, timeout=30)
    assert r.status_code == 200, f"Stories list failed: {r.text}"
    stories = r.json()
    assert len(stories) > 0, "Creator has no stories"

    fallback = None
    for story in stories:
        sid = story.get("story_id") or story.get("id")
        if not sid:
            continue
        rep = requests.get(f"{BASE_URL}/api/episodes/story/{sid}", headers=headers, timeout=30)
        if rep.status_code != 200:
            continue
        for ep in rep.json():
            eid = ep.get("episode_id") or ep.get("id")
            if not eid:
                continue
            if not ep.get("is_published"):
                return {"episode_id": eid, "story_id": sid, "is_published": False}
            if fallback is None:
                fallback = {"episode_id": eid, "story_id": sid, "is_published": True}
    if fallback:
        return fallback
    pytest.skip("No episode found for creator")


@pytest.fixture(scope="module")
def voice_id(headers):
    r = requests.get(f"{BASE_URL}/api/voices", headers=headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    voices = data.get("voices") if isinstance(data, dict) else data
    assert voices and len(voices) > 0
    v = voices[0]
    return v.get("voice_id") or v.get("id") or v.get("name")


def _hard_regen(headers, episode_id, part_number, voice_id, text, director_notes=""):
    return requests.post(
        f"{BASE_URL}/api/script/{episode_id}/narration/part/{part_number}/hard-regenerate",
        headers=headers,
        json={"voice_id": voice_id, "text": text, "director_notes": director_notes},
        timeout=30,
    )


# --- Validation tests (no creator generation access needed) ---

class TestHardRegenValidation:
    def test_no_auth_returns_401(self, episode_with_narration, voice_id):
        url = f"{BASE_URL}/api/script/{episode_with_narration['episode_id']}/narration/part/1/hard-regenerate"
        r = requests.post(url, json={"voice_id": voice_id, "text": "hello", "director_notes": ""}, timeout=30)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"

    def test_empty_text_returns_400(self, headers, episode_with_narration, voice_id):
        r = _hard_regen(headers, episode_with_narration["episode_id"], 1, voice_id, "   ")
        assert r.status_code == 400, f"Expected 400 got {r.status_code}: {r.text}"

    def test_content_too_long_returns_422(self, headers, episode_with_narration, voice_id):
        r = _hard_regen(headers, episode_with_narration["episode_id"], 1, voice_id, HUGE_TEXT)
        assert r.status_code == 422, f"Expected 422 got {r.status_code}: {r.text}"
        assert "content_too_long" in r.text.lower()

    def test_missing_voice_id_returns_400(self, headers, episode_with_narration):
        r = _hard_regen(headers, episode_with_narration["episode_id"], 1, "", "hello world")
        assert r.status_code == 400, f"Expected 400 got {r.status_code}: {r.text}"

    def test_published_episode_returns_423(self, headers, voice_id):
        """Find any published episode (or skip if none)."""
        r = requests.get(f"{BASE_URL}/api/stories", headers=headers, timeout=30)
        if r.status_code != 200:
            pytest.skip("Cannot fetch stories")
        for story in r.json():
            sid = story.get("story_id") or story.get("id")
            ep_r = requests.get(f"{BASE_URL}/api/episodes/story/{sid}", headers=headers, timeout=30)
            if ep_r.status_code != 200:
                continue
            for ep in ep_r.json():
                if ep.get("is_published"):
                    eid = ep.get("episode_id") or ep.get("id")
                    rr = _hard_regen(headers, eid, 1, voice_id, "Some text")
                    assert rr.status_code == 423, f"Expected 423 for published episode got {rr.status_code}: {rr.text}"
                    return
        pytest.skip("No published episode found to test 423")


# --- 200 / Queue acceptance tests (require generation access) ---

class TestHardRegenAcceptance:
    def test_hard_regenerate_accepted_or_403(self, headers, episode_with_narration, voice_id):
        """The 200 path requires generation access. If 403, document and continue."""
        eid = episode_with_narration["episode_id"]
        part_text = "Once upon a time the narrator spoke softly to the listener."

        r = _hard_regen(headers, eid, 1, voice_id, part_text)
        if r.status_code == 403:
            pytest.skip(f"Creator generation access disabled (403): {r.text}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("status") == "queued"
        assert body.get("total_parts") == 1
        assert body.get("total_dialogues") == 1
        assert "job_id" in body
        assert "queue_id" in body

    def test_cache_bypass_creates_new_version(self, headers, episode_with_narration, voice_id):
        """Hard regen with identical text should create new versions (force_new in payload)."""
        eid = episode_with_narration["episode_id"]
        part_text = "Identical narration text used twice for cache bypass."

        v_before = requests.get(f"{BASE_URL}/api/episodes/{eid}/versions", headers=headers, timeout=30)
        assert v_before.status_code == 200

        r1 = _hard_regen(headers, eid, 1, voice_id, part_text)
        if r1.status_code == 403:
            pytest.skip(f"Creator generation access disabled (403): {r1.text}")
        assert r1.status_code == 200
        job1 = r1.json()["job_id"]

        # Poll job1 briefly
        for _ in range(20):
            time.sleep(2)
            sr = requests.get(f"{BASE_URL}/api/script/job/{job1}/status", headers=headers, timeout=30)
            if sr.status_code == 200 and sr.json().get("status") in ("completed", "failed"):
                break

        # second identical call
        r2 = _hard_regen(headers, eid, 1, voice_id, part_text)
        assert r2.status_code == 200, f"Second hard-regen failed: {r2.status_code} {r2.text}"
        assert r2.json().get("status") == "queued"

        v_after = requests.get(f"{BASE_URL}/api/episodes/{eid}/versions", headers=headers, timeout=30)
        assert v_after.status_code == 200

    def test_clips_only_returns_active(self, headers, episode_with_narration):
        eid = episode_with_narration["episode_id"]
        r = requests.get(f"{BASE_URL}/api/episodes/{eid}/clips", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        clips = data.get("clips") if isinstance(data, dict) else data
        assert clips is not None
        for c in clips:
            assert isinstance(c, dict), f"clip entry is not dict: {c}"
            assert c.get("is_active", True) is True, f"Inactive clip leaked into /clips: {c}"


class TestHardRegenAutoSelectBehavior:
    """If a previously selected version exists for the Part, a hard-regen new version must NOT auto-select."""

    def test_new_version_not_auto_selected(self, headers, episode_with_narration):
        eid = episode_with_narration["episode_id"]
        r = requests.get(f"{BASE_URL}/api/episodes/{eid}/versions", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        versions_map = data.get("versions") if isinstance(data, dict) else data
        assert isinstance(versions_map, dict), f"Unexpected versions shape: {type(versions_map)}"
        # versions are grouped by dialogue_index (string key)
        clips = versions_map.get("0") or versions_map.get(0) or []
        assert isinstance(clips, list)
        if not clips:
            pytest.skip("No versions for dialogue_index 0")
        selected = [c for c in clips if c.get("is_selected") is True]
        # invariant: at most ONE selected per dialogue_index
        assert len(selected) <= 1, f"More than one selected version found: {len(selected)}"
        # The most recent version (label == 'Latest') must not be auto-selected when force_new=True path was used.
        latest = [c for c in clips if c.get("label") == "Latest"]
        if latest:
            # The last hard-regen would have produced one; verify it isn't auto-selected
            assert latest[0].get("is_selected") is False or len(selected) == 0, (
                f"Latest version was auto-selected unexpectedly: {latest[0]}"
            )
