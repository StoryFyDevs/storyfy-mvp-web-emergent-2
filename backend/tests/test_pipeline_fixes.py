"""
Tests for pipeline fixes (Issue 1 + Issue 2):
- Issue 1: Global speaker pair batching
- Issue 2: Safe fallback segmentation
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from script_compiler import (
    group_dialogues_by_speaker_pairs,
    _validate_batch,
    _build_multi_speaker_payload,
    _reconcile_utterances,
    INTER_LINE_PAUSE,
)


# ── ISSUE 1: Global Speaker Pair Batching ──

class TestGlobalPairBatching:
    """Test that batching groups all dialogues by unique speaker pairs globally."""

    def _make_dialogue(self, name, text, idx):
        return {"character_name": name, "text": text, "dialogue_index": idx}

    def test_user_test_case(self):
        """User's exact test case: 2 pairs, 8 dialogues → 2 batches."""
        dialogues = [
            self._make_dialogue("Devang", "Hello", 0),
            self._make_dialogue("Priya", "Hi", 1),
            self._make_dialogue("Devang", "Where were you?", 2),
            self._make_dialogue("Priya", "I was waiting", 3),
            self._make_dialogue("Jyoti", "Let's go", 4),
            self._make_dialogue("Rohan", "Okay", 5),
            self._make_dialogue("Jyoti", "Ready?", 6),
            self._make_dialogue("Rohan", "Yes", 7),
        ]
        batches = group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

        pair_keys = {tuple(sorted(b["speakers"])) for b in batches}
        assert ("Devang", "Priya") in pair_keys
        assert ("Jyoti", "Rohan") in pair_keys

        for b in batches:
            pk = tuple(sorted(b["speakers"]))
            if pk == ("Devang", "Priya"):
                assert len(b["dialogues"]) == 4
            elif pk == ("Jyoti", "Rohan"):
                assert len(b["dialogues"]) == 4

    def test_interleaved_conversations(self):
        """Conversations interleaved: Devang+Priya and Jyoti+Rohan mixed."""
        dialogues = [
            self._make_dialogue("Devang", "Hello", 0),
            self._make_dialogue("Priya", "Hi", 1),
            self._make_dialogue("Jyoti", "Let's go", 2),
            self._make_dialogue("Rohan", "Okay", 3),
            self._make_dialogue("Devang", "Where?", 4),
            self._make_dialogue("Priya", "Waiting", 5),
            self._make_dialogue("Jyoti", "Ready?", 6),
            self._make_dialogue("Rohan", "Yes", 7),
        ]
        batches = group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

        pair_keys = {tuple(sorted(b["speakers"])) for b in batches}
        assert ("Devang", "Priya") in pair_keys
        assert ("Jyoti", "Rohan") in pair_keys

    def test_speaker_reuse_batching(self):
        """Same pair appearing multiple times → single batch."""
        dialogues = [
            self._make_dialogue("Devang", "Line 1", 0),
            self._make_dialogue("Priya", "Line 2", 1),
            self._make_dialogue("Devang", "Line 3", 2),
            self._make_dialogue("Priya", "Line 4", 3),
        ]
        batches = group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 1
        assert len(batches[0]["dialogues"]) == 4

    def test_pair_key_deterministic(self):
        """pair_key = sorted(A, B) regardless of who speaks first."""
        dialogues_ab = [
            self._make_dialogue("Alpha", "Hello", 0),
            self._make_dialogue("Beta", "Hi", 1),
        ]
        dialogues_ba = [
            self._make_dialogue("Beta", "Hello", 0),
            self._make_dialogue("Alpha", "Hi", 1),
        ]
        batches_ab = group_dialogues_by_speaker_pairs(dialogues_ab)
        batches_ba = group_dialogues_by_speaker_pairs(dialogues_ba)

        key_ab = tuple(sorted(batches_ab[0]["speakers"]))
        key_ba = tuple(sorted(batches_ba[0]["speakers"]))
        assert key_ab == key_ba == ("Alpha", "Beta")

    def test_single_speaker(self):
        """All dialogues from one speaker → 1 batch with 1 speaker."""
        dialogues = [
            self._make_dialogue("Narrator", "Line 1", 0),
            self._make_dialogue("Narrator", "Line 2", 1),
        ]
        batches = group_dialogues_by_speaker_pairs(dialogues)
        assert len(batches) == 1
        assert len(batches[0]["speakers"]) == 1

    def test_empty_input(self):
        assert group_dialogues_by_speaker_pairs([]) == []

    def test_single_dialogue(self):
        dialogues = [self._make_dialogue("Solo", "Hello", 0)]
        batches = group_dialogues_by_speaker_pairs(dialogues)
        assert len(batches) == 1
        assert len(batches[0]["dialogues"]) == 1


# ── ISSUE 1 continued: Validate batch still works ──

class TestValidateBatch:
    def test_valid_batch(self):
        batch = {
            "speakers": ["Devang", "Jyoti"],
            "dialogues": [
                {"character_name": "Devang", "text": "Hello", "dialogue_index": 0},
                {"character_name": "Jyoti", "text": "Hi", "dialogue_index": 1},
            ]
        }
        voice_map = {"Devang": "Kore", "Jyoti": "Puck"}
        assert _validate_batch(batch, voice_map) is None

    def test_empty_dialogues(self):
        batch = {"speakers": ["Devang", "Jyoti"], "dialogues": []}
        assert _validate_batch(batch, {"Devang": "Kore", "Jyoti": "Puck"}) is not None

    def test_missing_voice_id(self):
        batch = {"speakers": ["Devang", "Jyoti"], "dialogues": [{"text": "Hello"}]}
        assert _validate_batch(batch, {"Devang": "Kore"}) is not None


# ── ISSUE 2: Safe Fallback Segmentation ──

class TestSafeSegmentation:
    """Test that reconciliation never produces timestamps beyond audio duration."""

    def test_exact_match(self):
        utts = [
            {"speaker": 0, "start": 0, "end": 1, "transcript": "Hello"},
            {"speaker": 1, "start": 1, "end": 2, "transcript": "Hi"},
        ]
        result = _reconcile_utterances(utts, 2, "test", audio_duration=2.0)
        assert result is not None
        assert len(result) == 2

    def test_merge_same_speaker(self):
        utts = [
            {"speaker": 0, "start": 0, "end": 0.5, "transcript": "Hel"},
            {"speaker": 0, "start": 0.5, "end": 1, "transcript": "lo"},
            {"speaker": 1, "start": 1, "end": 2, "transcript": "Hi"},
        ]
        result = _reconcile_utterances(utts, 2, "test", audio_duration=2.0)
        assert result is not None
        assert len(result) == 2

    def test_equal_division_for_fewer_segments(self):
        """When Deepgram returns 1 segment but need 4 → equal division."""
        utts = [
            {"speaker": 0, "start": 0, "end": 13.53, "transcript": "All text together"},
        ]
        result = _reconcile_utterances(utts, 4, "test", audio_duration=13.53)
        assert result is not None
        assert len(result) == 4

        # Verify NO timestamp exceeds audio_duration
        for seg in result:
            assert seg["start"] >= 0, f"Start {seg['start']} is negative"
            assert seg["end"] <= 13.53, f"End {seg['end']} exceeds audio duration 13.53"
            assert seg["start"] < seg["end"], f"Start {seg['start']} >= End {seg['end']}"

    def test_equal_division_timestamps_are_correct(self):
        """Verify equal-division produces expected timestamps."""
        utts = [
            {"speaker": 0, "start": 0, "end": 12.0, "transcript": "All"},
        ]
        result = _reconcile_utterances(utts, 4, "test", audio_duration=12.0)
        assert result is not None
        assert len(result) == 4

        # Each segment should be 3.0s
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 3.0
        assert result[1]["start"] == 3.0
        assert result[1]["end"] == 6.0
        assert result[2]["start"] == 6.0
        assert result[2]["end"] == 9.0
        assert result[3]["start"] == 9.0
        assert result[3]["end"] == 12.0

    def test_timestamps_never_exceed_duration(self):
        """Critical: timestamps must never exceed audio_duration, even with rounding."""
        utts = [
            {"speaker": 0, "start": 0, "end": 10.0, "transcript": "text"},
        ]
        # 7 segments from 10s audio → 1.4285...s each
        result = _reconcile_utterances(utts, 7, "test", audio_duration=10.0)
        assert result is not None
        assert len(result) == 7

        for seg in result:
            assert seg["end"] <= 10.0, f"Segment end {seg['end']} exceeds 10.0s"

    def test_aggressive_merge_too_many(self):
        utts = [
            {"speaker": 0, "start": 0, "end": 1, "transcript": "A"},
            {"speaker": 1, "start": 1, "end": 2, "transcript": "B"},
            {"speaker": 0, "start": 2, "end": 3, "transcript": "C"},
            {"speaker": 1, "start": 3, "end": 4, "transcript": "D"},
            {"speaker": 0, "start": 4, "end": 5, "transcript": "E"},
        ]
        result = _reconcile_utterances(utts, 3, "test", audio_duration=5.0)
        assert result is not None
        assert len(result) == 3

    def test_empty_utterances(self):
        result = _reconcile_utterances([], 4, "test", audio_duration=10.0)
        assert result is None

    def test_no_audio_duration_falls_back(self):
        """Without audio_duration, can't do equal-division → returns None."""
        utts = [
            {"speaker": 0, "start": 0, "end": 10, "transcript": "text"},
        ]
        result = _reconcile_utterances(utts, 4, "test", audio_duration=0)
        assert result is None


# ── Payload construction still works ──

class TestBuildMultiSpeakerPayload:
    def test_pause_markers(self):
        batch = {
            "speakers": ["A", "B"],
            "dialogues": [
                {"character_name": "A", "text": "Hello", "dialogue_index": 0},
                {"character_name": "B", "text": "Hi", "dialogue_index": 1},
            ]
        }
        payload = _build_multi_speaker_payload(batch, {"A": "Kore", "B": "Puck"}, {})
        text = payload["contents"][0]["parts"][0]["text"]
        assert INTER_LINE_PAUSE in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
