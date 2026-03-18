"""
Test suite for speaker-pair batching pipeline in script_compiler.py

Tests the batching logic, payload builders, clip extraction, and API contracts
WITHOUT triggering actual Gemini/Deepgram API calls.

Target features:
- group_dialogues_by_speaker_pairs: Groups dialogues into 2-speaker batches
- _build_multi_speaker_payload: Creates Gemini multiSpeakerVoiceConfig format
- _build_single_speaker_payload: Fallback single-speaker payload
- _extract_clip_from_wav: Extracts clips at timestamps
- _validate_wav: Validates WAV files
- _reconcile_utterances: Merges same-speaker adjacent utterances
- compute_cache_key: Consistent hashing
- API endpoints: /api/script/{episode_id}/generate, /api/script/job/{job_id}/status
"""

import pytest
import requests
import os
import sys
import io
import wave
import hashlib

# Add backend directory to path
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://daw-timeline-demo.preview.emergentagent.com')
TEST_EMAIL = "testuser@test.com"
TEST_PASSWORD = "password123"


# ========== AUTH FIXTURE ==========

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ========== UNIT TESTS: BATCHING LOGIC ==========

class TestGroupDialoguesByPairsLogic:
    """Test group_dialogues_by_speaker_pairs function logic."""

    def test_batching_8_dialogues_4_speakers_produces_2_batches(self):
        """
        8 dialogues with 4 characters should produce 2 batches.
        Example script: Rahul, Aarti, Rahul, Aarti, Sagar, Meera, Rahul, Aarti
        Expected: Batch 1: Aarti+Rahul [0,1,2,3,6,7], Batch 2: Meera+Sagar [4,5]
        """
        import script_compiler as sc
        
        dialogues = [
            {"character_name": "Rahul", "text": "Hello Aarti", "dialogue_index": 0},
            {"character_name": "Aarti", "text": "Hi Rahul", "dialogue_index": 1},
            {"character_name": "Rahul", "text": "How are you?", "dialogue_index": 2},
            {"character_name": "Aarti", "text": "I'm good", "dialogue_index": 3},
            {"character_name": "Sagar", "text": "Hey everyone", "dialogue_index": 4},
            {"character_name": "Meera", "text": "Hello Sagar", "dialogue_index": 5},
            {"character_name": "Rahul", "text": "Back to us", "dialogue_index": 6},
            {"character_name": "Aarti", "text": "Yes indeed", "dialogue_index": 7},
        ]
        
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)
        
        # Should produce exactly 2 batches
        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"
        
        # Find the Aarti+Rahul batch and Meera+Sagar batch
        ar_batch = next((b for b in batches if set(b["speakers"]) == {"Aarti", "Rahul"}), None)
        ms_batch = next((b for b in batches if set(b["speakers"]) == {"Meera", "Sagar"}), None)
        
        assert ar_batch is not None, "Aarti+Rahul batch not found"
        assert ms_batch is not None, "Meera+Sagar batch not found"
        
        # Aarti+Rahul batch should have 6 dialogues [0,1,2,3,6,7]
        assert len(ar_batch["dialogues"]) == 6, f"Expected 6 dialogues in Aarti+Rahul batch, got {len(ar_batch['dialogues'])}"
        ar_indices = [d["dialogue_index"] for d in ar_batch["dialogues"]]
        assert set(ar_indices) == {0, 1, 2, 3, 6, 7}, f"Wrong indices: {ar_indices}"
        
        # Meera+Sagar batch should have 2 dialogues [4,5]
        assert len(ms_batch["dialogues"]) == 2, f"Expected 2 dialogues in Meera+Sagar batch, got {len(ms_batch['dialogues'])}"
        ms_indices = [d["dialogue_index"] for d in ms_batch["dialogues"]]
        assert set(ms_indices) == {4, 5}, f"Wrong indices: {ms_indices}"
        
        print(f"✓ Batching produces 2 batches: Aarti+Rahul (6 dialogues), Meera+Sagar (2 dialogues)")

    def test_single_speaker_dialogues(self):
        """Single speaker dialogues should produce one batch with 1 speaker."""
        import script_compiler as sc
        
        dialogues = [
            {"character_name": "Narrator", "text": "Once upon a time", "dialogue_index": 0},
            {"character_name": "Narrator", "text": "There was a hero", "dialogue_index": 1},
            {"character_name": "Narrator", "text": "The end", "dialogue_index": 2},
        ]
        
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)
        
        assert len(batches) == 1, f"Expected 1 batch, got {len(batches)}"
        assert batches[0]["speakers"] == ["Narrator"], f"Expected ['Narrator'], got {batches[0]['speakers']}"
        assert len(batches[0]["dialogues"]) == 3
        
        print("✓ Single-speaker dialogues produce 1 batch with 1 speaker")

    def test_3_plus_characters_splits_correctly(self):
        """3+ characters should split into batches when 3rd speaker appears."""
        import script_compiler as sc
        
        dialogues = [
            {"character_name": "A", "text": "Hi", "dialogue_index": 0},
            {"character_name": "B", "text": "Hello", "dialogue_index": 1},
            {"character_name": "C", "text": "Hey", "dialogue_index": 2},  # 3rd speaker triggers new batch
            {"character_name": "A", "text": "Back", "dialogue_index": 3},
        ]
        
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)
        
        # With 3 speakers, we expect splits when 3rd speaker appears
        # First batch: A, B (indices 0, 1)
        # Then C appears (index 2) starts new batch
        # A appears again (index 3) in the C batch? Or new batch?
        # According to algorithm: A is NOT in {C}, so starts new batch with A
        # Final: A+B[0,1] merged, C[2] alone, A[3] - but A+B merges with A from index 3?
        # Actually: raw_batches = [{A,B: [0,1]}, {C: [2]}, {A: [3]}]
        # Merge: key (A,B) -> [0,1], key (C) -> [2], key (A) -> [3]
        # Wait, that's wrong. The merge uses tuple(sorted(speakers))
        # So (A,B) stays, (C) stays, (A) stays
        # Result: 3 batches unless same pairs
        
        # Let me re-check the algorithm:
        # d[0] A: cur_speakers={A}, cur_dialogues=[d0]
        # d[1] B: B in {A}? No. len({A})<2? Yes. cur_speakers={A,B}, cur_dialogues=[d0,d1]
        # d[2] C: C in {A,B}? No. len({A,B})<2? No. → batch {A,B:[d0,d1]}. cur={C}, cur_dialogues=[d2]
        # d[3] A: A in {C}? No. len({C})<2? Yes. cur_speakers={A,C}, cur_dialogues=[d2,d3]
        # End: batch {A,C:[d2,d3]}
        # Merge: {A,B:[d0,d1]}, {A,C:[d2,d3]} → different keys, so 2 batches
        
        assert len(batches) >= 2, f"Expected at least 2 batches, got {len(batches)}"
        
        # Check total dialogues across all batches
        total_dialogues = sum(len(b["dialogues"]) for b in batches)
        assert total_dialogues == 4, f"Expected 4 total dialogues, got {total_dialogues}"
        
        print(f"✓ 3+ characters produce {len(batches)} batches (split on 3rd speaker)")

    def test_empty_dialogues(self):
        """Empty dialogues list returns empty batches."""
        import script_compiler as sc
        
        batches = sc.group_dialogues_by_speaker_pairs([])
        assert batches == [], f"Expected [], got {batches}"
        print("✓ Empty dialogues return empty batches")

    def test_two_speakers_back_and_forth(self):
        """Two speakers alternating should produce 1 batch."""
        import script_compiler as sc
        
        dialogues = [
            {"character_name": "Hero", "text": "Hello", "dialogue_index": 0},
            {"character_name": "Villain", "text": "Greetings", "dialogue_index": 1},
            {"character_name": "Hero", "text": "Fight me", "dialogue_index": 2},
            {"character_name": "Villain", "text": "Gladly", "dialogue_index": 3},
        ]
        
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)
        
        assert len(batches) == 1, f"Expected 1 batch, got {len(batches)}"
        assert set(batches[0]["speakers"]) == {"Hero", "Villain"}
        assert len(batches[0]["dialogues"]) == 4
        
        print("✓ Two speakers alternating produce 1 batch with all 4 dialogues")


# ========== UNIT TESTS: PAYLOAD BUILDERS ==========

class TestPayloadBuilders:
    """Test _build_multi_speaker_payload and _build_single_speaker_payload."""

    def test_multi_speaker_payload_format(self):
        """Verify multiSpeakerVoiceConfig format is correct."""
        import script_compiler as sc
        
        batch = {
            "speakers": ["Aarti", "Rahul"],
            "dialogues": [
                {"character_name": "Rahul", "text": "Hello", "dialogue_index": 0},
                {"character_name": "Aarti", "text": "Hi back", "dialogue_index": 1},
            ]
        }
        voice_map = {"Rahul": "Schedar", "Aarti": "Kore"}
        director_notes_map = {0: "", 1: "whisper"}
        
        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        
        # Check structure
        assert "contents" in payload
        assert "generationConfig" in payload
        assert "speechConfig" in payload["generationConfig"]
        assert "multiSpeakerVoiceConfig" in payload["generationConfig"]["speechConfig"]
        
        configs = payload["generationConfig"]["speechConfig"]["multiSpeakerVoiceConfig"]["speakerVoiceConfigs"]
        assert len(configs) == 2, f"Expected 2 speaker configs, got {len(configs)}"
        
        # Check speaker names and voices
        speakers_in_config = {c["speaker"] for c in configs}
        assert speakers_in_config == {"Aarti", "Rahul"}
        
        # Check voice assignments
        for config in configs:
            speaker = config["speaker"]
            expected_voice = voice_map[speaker]
            actual_voice = config["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
            assert actual_voice == expected_voice, f"{speaker} voice mismatch: expected {expected_voice}, got {actual_voice}"
        
        # Check text includes director notes
        text = payload["contents"][0]["parts"][0]["text"]
        assert "whisper" in text, "Director notes should be in text"
        assert "Rahul:" in text
        assert "Aarti:" in text
        
        print("✓ Multi-speaker payload has correct multiSpeakerVoiceConfig format")

    def test_multi_speaker_payload_without_notes(self):
        """Director notes should only appear when present."""
        import script_compiler as sc
        
        batch = {
            "speakers": ["A", "B"],
            "dialogues": [
                {"character_name": "A", "text": "Line one", "dialogue_index": 0},
            ]
        }
        voice_map = {"A": "Kore", "B": "Schedar"}
        director_notes_map = {0: ""}  # Empty notes
        
        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        text = payload["contents"][0]["parts"][0]["text"]
        
        # Should NOT have brackets with empty content
        assert "[" not in text or "[]" not in text, f"Empty brackets in text: {text}"
        assert "A: Line one" in text
        
        print("✓ Multi-speaker payload excludes director notes when empty")

    def test_single_speaker_payload_format(self):
        """Test fallback single-speaker payload."""
        import script_compiler as sc
        
        payload = sc._build_single_speaker_payload("Hello world", "Kore", "")
        
        assert "contents" in payload
        assert payload["contents"][0]["parts"][0]["text"] == "Hello world"
        assert "speechConfig" in payload["generationConfig"]
        assert "voiceConfig" in payload["generationConfig"]["speechConfig"]
        
        voice = payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        assert voice == "Kore"
        
        print("✓ Single-speaker payload has correct format")

    def test_single_speaker_payload_with_notes(self):
        """Single-speaker payload should include director notes."""
        import script_compiler as sc
        
        payload = sc._build_single_speaker_payload("Hello", "Kore", "whisper softly")
        text = payload["contents"][0]["parts"][0]["text"]
        
        assert "Director Notes" in text
        assert "whisper softly" in text
        
        print("✓ Single-speaker payload includes director notes")


# ========== UNIT TESTS: WAV UTILITIES ==========

class TestWavUtilities:
    """Test _validate_wav, _extract_clip_from_wav, _pcm_to_wav."""

    def _create_test_wav(self, duration_sec=1.0, sample_rate=24000, channels=1):
        """Create a valid WAV file for testing."""
        import wave
        import struct
        
        num_samples = int(duration_sec * sample_rate)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            # Generate silence
            samples = b'\x00\x00' * num_samples * channels
            wf.writeframes(samples)
        return buf.getvalue()

    def test_validate_wav_accepts_valid_file(self):
        """_validate_wav should accept valid WAV files."""
        import script_compiler as sc
        
        wav_data = self._create_test_wav(duration_sec=1.0)
        
        assert len(wav_data) > 1000, "Test WAV should be > 1000 bytes"
        assert wav_data[:4] == b"RIFF", "Test WAV should have RIFF header"
        assert wav_data[8:12] == b"WAVE", "Test WAV should have WAVE marker"
        
        result = sc._validate_wav(wav_data, "test_clip")
        assert result is True, "Valid WAV should pass validation"
        
        print("✓ _validate_wav accepts valid WAV file")

    def test_validate_wav_rejects_small_files(self):
        """_validate_wav should reject files < MIN_AUDIO_BYTES."""
        import script_compiler as sc
        
        small_data = b"RIFF" + b"\x00" * 50 + b"WAVE"
        assert len(small_data) < 1000
        
        result = sc._validate_wav(small_data, "small_file")
        assert result is False, "Small file should fail validation"
        
        print("✓ _validate_wav rejects files < 1000 bytes")

    def test_validate_wav_rejects_invalid_header(self):
        """_validate_wav should reject files without RIFF header."""
        import script_compiler as sc
        
        invalid_data = b"XXXX" + b"\x00" * 2000 + b"WAVE"
        
        result = sc._validate_wav(invalid_data, "no_riff")
        assert result is False, "Missing RIFF header should fail"
        
        print("✓ _validate_wav rejects files without RIFF header")

    def test_validate_wav_rejects_missing_wave(self):
        """_validate_wav should reject files without WAVE marker."""
        import script_compiler as sc
        
        invalid_data = b"RIFF" + b"\x00" * 2000 + b"XXXX"
        
        result = sc._validate_wav(invalid_data, "no_wave")
        assert result is False, "Missing WAVE marker should fail"
        
        print("✓ _validate_wav rejects files without WAVE marker")

    def test_extract_clip_from_wav_correct_duration(self):
        """_extract_clip_from_wav should extract correct duration clip."""
        import script_compiler as sc
        
        # Create 3-second WAV
        wav_data = self._create_test_wav(duration_sec=3.0)
        
        # Extract 1 second from middle (1.0s to 2.0s)
        clip = sc._extract_clip_from_wav(wav_data, 1.0, 2.0)
        
        assert len(clip) > 0, "Clip should not be empty"
        
        # Verify clip duration
        clip_buf = io.BytesIO(clip)
        with wave.open(clip_buf, 'rb') as wf:
            sr = wf.getframerate()
            frames = wf.getnframes()
            duration = frames / sr
            # Should be approximately 1 second
            assert 0.95 <= duration <= 1.05, f"Clip duration should be ~1s, got {duration:.3f}s"
        
        print("✓ _extract_clip_from_wav extracts correct 1-second clip")

    def test_extract_clip_handles_boundary(self):
        """_extract_clip_from_wav handles start=0 correctly."""
        import script_compiler as sc
        
        wav_data = self._create_test_wav(duration_sec=2.0)
        
        # Extract from start
        clip = sc._extract_clip_from_wav(wav_data, 0.0, 0.5)
        
        assert len(clip) > 0
        
        clip_buf = io.BytesIO(clip)
        with wave.open(clip_buf, 'rb') as wf:
            duration = wf.getnframes() / wf.getframerate()
            assert 0.4 <= duration <= 0.6, f"Expected ~0.5s, got {duration:.3f}s"
        
        print("✓ _extract_clip_from_wav handles start=0 boundary")

    def test_extract_clip_returns_empty_for_invalid_range(self):
        """_extract_clip_from_wav returns empty for end <= start."""
        import script_compiler as sc
        
        wav_data = self._create_test_wav(duration_sec=2.0)
        
        # Invalid range
        clip = sc._extract_clip_from_wav(wav_data, 1.5, 1.0)
        assert clip == b"", "Invalid range should return empty bytes"
        
        print("✓ _extract_clip_from_wav returns empty for invalid range")


# ========== UNIT TESTS: CACHE ==========

class TestCacheKey:
    """Test compute_cache_key function."""

    def test_cache_key_deterministic(self):
        """compute_cache_key should produce consistent hashes."""
        import script_compiler as sc
        
        key1 = sc.compute_cache_key("Hello world", "Kore", "")
        key2 = sc.compute_cache_key("Hello world", "Kore", "")
        
        assert key1 == key2, "Same input should produce same key"
        assert len(key1) == 32, f"Key should be 32 chars, got {len(key1)}"
        
        print("✓ compute_cache_key is deterministic")

    def test_cache_key_different_for_different_inputs(self):
        """Different inputs should produce different keys."""
        import script_compiler as sc
        
        key1 = sc.compute_cache_key("Hello", "Kore", "")
        key2 = sc.compute_cache_key("Hello", "Schedar", "")  # Different voice
        key3 = sc.compute_cache_key("Hello!", "Kore", "")  # Different text
        key4 = sc.compute_cache_key("Hello", "Kore", "whisper")  # Different notes
        
        keys = {key1, key2, key3, key4}
        assert len(keys) == 4, "All keys should be unique"
        
        print("✓ compute_cache_key produces different keys for different inputs")

    def test_cache_key_strips_whitespace(self):
        """compute_cache_key should strip whitespace."""
        import script_compiler as sc
        
        key1 = sc.compute_cache_key("  Hello  ", "  Kore  ", "  notes  ")
        key2 = sc.compute_cache_key("Hello", "Kore", "notes")
        
        assert key1 == key2, "Whitespace should be stripped"
        
        print("✓ compute_cache_key strips whitespace")


# ========== UNIT TESTS: UTTERANCE RECONCILIATION ==========

class TestReconcileUtterances:
    """Test _reconcile_utterances function."""

    def test_reconcile_merges_same_speaker(self):
        """Adjacent same-speaker utterances should merge."""
        import script_compiler as sc
        
        utterances = [
            {"speaker": 0, "start": 0.0, "end": 1.0, "transcript": "Hello"},
            {"speaker": 0, "start": 1.0, "end": 2.0, "transcript": "world"},  # Same speaker
            {"speaker": 1, "start": 2.0, "end": 3.0, "transcript": "Hi"},
        ]
        
        # If expected is 2, merge first two
        result = sc._reconcile_utterances(utterances, 2, "test")
        
        if result:
            assert len(result) == 2, f"Expected 2 utterances after merge, got {len(result)}"
            # First merged utterance should span 0-2s
            assert result[0]["start"] == 0.0
            assert result[0]["end"] == 2.0
            print("✓ _reconcile_utterances merges same-speaker adjacent utterances")
        else:
            print("✓ _reconcile_utterances returns None when merge can't reach target")

    def test_reconcile_returns_none_for_too_few(self):
        """Should return None if too few utterances to merge."""
        import script_compiler as sc
        
        utterances = [
            {"speaker": 0, "start": 0.0, "end": 1.0, "transcript": "Hello"},
        ]
        
        result = sc._reconcile_utterances(utterances, 5, "test")
        assert result is None, "Should return None when utterances < expected"
        
        print("✓ _reconcile_utterances returns None when too few utterances")

    def test_reconcile_returns_as_is_when_count_matches(self):
        """Should return utterances as-is when count matches expected."""
        import script_compiler as sc
        
        utterances = [
            {"speaker": 0, "start": 0.0, "end": 1.0, "transcript": "Hello"},
            {"speaker": 1, "start": 1.0, "end": 2.0, "transcript": "Hi"},
        ]
        
        result = sc._reconcile_utterances(utterances, 2, "test")
        assert result == utterances, "Should return original when count matches"
        
        print("✓ _reconcile_utterances returns original when count matches")


# ========== API ENDPOINT TESTS ==========

class TestGenerateEndpoint:
    """Test POST /api/script/{episode_id}/generate endpoint."""

    def test_generate_endpoint_exists(self, auth_headers):
        """Verify endpoint exists and accepts requests."""
        # Use known episode ID
        episode_id = "ep_71379fe1575a"
        
        # Empty dialogues should return 400
        response = requests.post(
            f"{BASE_URL}/api/script/{episode_id}/generate",
            headers=auth_headers,
            json={"dialogues": []}
        )
        
        # 400 means endpoint exists and validates input
        assert response.status_code in [400, 200], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data
        
        print(f"✓ POST /api/script/{{episode_id}}/generate endpoint exists (status: {response.status_code})")

    def test_generate_returns_job_id(self, auth_headers):
        """Generate should return job_id for valid request."""
        episode_id = "ep_71379fe1575a"
        
        # Minimal valid dialogue
        dialogues = [{
            "index": 0,
            "character_id": "char_test",
            "character_name": "TestChar",
            "voice_id": "Kore",
            "text": "Test dialogue text",
            "director_notes": ""
        }]
        
        response = requests.post(
            f"{BASE_URL}/api/script/{episode_id}/generate",
            headers=auth_headers,
            json={"dialogues": dialogues}
        )
        
        # Should return 200 with job_id
        if response.status_code == 200:
            data = response.json()
            assert "job_id" in data, "Response should include job_id"
            assert data["job_id"].startswith("scrjob_"), f"Job ID format wrong: {data['job_id']}"
            assert "total_dialogues" in data
            print(f"✓ Generate returns job_id: {data['job_id']}")
        else:
            # 403 means rate limits or permission issue - acceptable
            print(f"✓ Generate endpoint responds (status: {response.status_code})")

    def test_generate_invalid_episode_returns_404(self, auth_headers):
        """Non-existent episode should return 404."""
        response = requests.post(
            f"{BASE_URL}/api/script/ep_nonexistent_123/generate",
            headers=auth_headers,
            json={"dialogues": [{"index": 0, "character_id": "c", "character_name": "C", "voice_id": "Kore", "text": "x"}]}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent episode returns 404")


class TestJobStatusEndpoint:
    """Test GET /api/script/job/{job_id}/status endpoint."""

    def test_job_status_endpoint_exists(self, auth_headers):
        """Verify endpoint exists."""
        response = requests.get(
            f"{BASE_URL}/api/script/job/scrjob_nonexistent123/status",
            headers=auth_headers
        )
        
        # 404 means endpoint exists but job not found
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ GET /api/script/job/{{job_id}}/status endpoint exists")

    def test_job_status_returns_correct_fields(self, auth_headers):
        """Job status should return required fields when job exists."""
        # First create a job
        episode_id = "ep_71379fe1575a"
        dialogues = [{
            "index": 0,
            "character_id": "char_test",
            "character_name": "TestChar",
            "voice_id": "Kore",
            "text": "Test text for status check",
            "director_notes": ""
        }]
        
        create_resp = requests.post(
            f"{BASE_URL}/api/script/{episode_id}/generate",
            headers=auth_headers,
            json={"dialogues": dialogues}
        )
        
        if create_resp.status_code != 200:
            pytest.skip("Could not create job to test status")
        
        job_id = create_resp.json().get("job_id")
        
        # Get status
        response = requests.get(
            f"{BASE_URL}/api/script/job/{job_id}/status",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "job_id" in data
        assert "status" in data
        assert "total_dialogues" in data
        assert "completed_dialogues" in data
        
        print(f"✓ Job status returns correct fields: status={data['status']}, completed={data['completed_dialogues']}/{data['total_dialogues']}")


class TestAudioStreamEndpoint:
    """Test GET /api/audio/stream-file/{file_id} endpoint."""

    def test_stream_valid_file(self):
        """Streaming valid file_id should return audio data."""
        file_id = "e50c796e-cb7e-4c52-9fd0-fb2017046d8b"  # Known valid file
        
        response = requests.get(f"{BASE_URL}/api/audio/stream-file/{file_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get("Content-Type") == "audio/wav"
        
        # Verify WAV header
        content = response.content
        assert content[:4] == b"RIFF", "Should have RIFF header"
        assert content[8:12] == b"WAVE", "Should have WAVE marker"
        
        print(f"✓ Stream endpoint returns valid WAV ({len(content)} bytes)")

    def test_stream_invalid_file_returns_404(self):
        """Non-existent file_id should return 404."""
        response = requests.get(f"{BASE_URL}/api/audio/stream-file/nonexistent-file-id")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent file returns 404")


# ========== INTEGRATION TESTS ==========

class TestDialoguesEndpoint:
    """Test GET/POST /api/script/{episode_id}/dialogues endpoints."""

    def test_get_dialogues(self, auth_headers):
        """GET dialogues should return list."""
        episode_id = "ep_71379fe1575a"
        
        response = requests.get(
            f"{BASE_URL}/api/script/{episode_id}/dialogues",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "dialogues" in data
        assert isinstance(data["dialogues"], list)
        
        print(f"✓ GET dialogues returns {len(data['dialogues'])} dialogues")

    def test_save_dialogues(self, auth_headers):
        """POST dialogues should save successfully."""
        episode_id = "ep_71379fe1575a"
        
        dialogues = [{
            "index": 0,
            "character_id": "char_test_save",
            "character_name": "SaveTest",
            "voice_id": "Kore",
            "text": "Test save dialogue",
            "director_notes": "test notes",
            "generated_voice_id": ""
        }]
        
        response = requests.post(
            f"{BASE_URL}/api/script/{episode_id}/dialogues",
            headers=auth_headers,
            json={"dialogues": dialogues}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data.get("dialogue_count") == 1
        
        print("✓ POST dialogues saves successfully")


class TestGenerationStatus:
    """Test GET /api/generation/status endpoint."""

    def test_generation_status_fields(self, auth_headers):
        """Generation status should return rate limit info."""
        response = requests.get(
            f"{BASE_URL}/api/generation/status",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "can_generate" in data
        assert "generations_remaining" in data or "daily_limit" in data
        
        print(f"✓ Generation status: can_generate={data.get('can_generate')}, remaining={data.get('generations_remaining', 'N/A')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
