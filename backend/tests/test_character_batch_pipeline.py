"""
Unit tests for the character-based batch generation pipeline.

Tests:
1. Character batching: group_dialogues_by_character
2. Payload builder: _build_character_batch_payload
3. Text alignment: _align_transcription_with_dialogues
4. Token normalization: _normalize_to_tokens, _normalize_word, _words_similar
5. Punctuation enforcement: _ensure_punctuation
6. WAV utilities: regression
7. Cache: regression
"""
import sys
sys.path.insert(0, '/app/backend')

import pytest
import io
import wave
import script_compiler as sc


# ============================================================
# CHARACTER BATCHING
# ============================================================

class TestGroupDialoguesByCharacter:
    """Test group_dialogues_by_character function."""

    def test_groups_by_character_name(self):
        """Dialogues grouped by character, each character gets 1 batch."""
        dialogues = [
            {"character_name": "Devang", "text": "Hello.", "dialogue_index": 0},
            {"character_name": "Priya", "text": "Hi.", "dialogue_index": 1},
            {"character_name": "Devang", "text": "How are you?", "dialogue_index": 2},
            {"character_name": "Priya", "text": "Fine.", "dialogue_index": 3},
        ]
        batches = sc.group_dialogues_by_character(dialogues)

        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

        devang = next(b for b in batches if b["character"] == "Devang")
        priya = next(b for b in batches if b["character"] == "Priya")

        assert len(devang["dialogues"]) == 2
        assert len(priya["dialogues"]) == 2

        devang_indices = [d["dialogue_index"] for d in devang["dialogues"]]
        assert devang_indices == [0, 2]
        priya_indices = [d["dialogue_index"] for d in priya["dialogues"]]
        assert priya_indices == [1, 3]
        print("PASS: Groups by character name correctly")

    def test_4_characters_produce_4_batches(self):
        """4 unique characters → 4 batches → 4 Gemini calls."""
        dialogues = [
            {"character_name": "Devang", "text": "Hello", "dialogue_index": 0},
            {"character_name": "Priya", "text": "Hi", "dialogue_index": 1},
            {"character_name": "Jyoti", "text": "How are you?", "dialogue_index": 2},
            {"character_name": "Rohan", "text": "I'm fine", "dialogue_index": 3},
            {"character_name": "Devang", "text": "Where were you?", "dialogue_index": 4},
            {"character_name": "Priya", "text": "I was waiting.", "dialogue_index": 5},
        ]
        batches = sc.group_dialogues_by_character(dialogues)

        assert len(batches) == 4
        chars = {b["character"] for b in batches}
        assert chars == {"Devang", "Priya", "Jyoti", "Rohan"}

        devang = next(b for b in batches if b["character"] == "Devang")
        assert len(devang["dialogues"]) == 2
        assert [d["dialogue_index"] for d in devang["dialogues"]] == [0, 4]
        print("PASS: 4 characters → 4 batches")

    def test_single_character(self):
        """All dialogues from 1 character → 1 batch."""
        dialogues = [
            {"character_name": "Narrator", "text": "Once upon a time.", "dialogue_index": 0},
            {"character_name": "Narrator", "text": "The end.", "dialogue_index": 1},
        ]
        batches = sc.group_dialogues_by_character(dialogues)
        assert len(batches) == 1
        assert batches[0]["character"] == "Narrator"
        assert len(batches[0]["dialogues"]) == 2
        print("PASS: Single character → 1 batch")

    def test_empty_dialogues(self):
        """Empty input → empty output."""
        assert sc.group_dialogues_by_character([]) == []
        print("PASS: Empty dialogues → empty batches")

    def test_preserves_all_dialogues(self):
        """Total dialogue count across batches matches input."""
        dialogues = [
            {"character_name": "A", "text": "1", "dialogue_index": i}
            for i in range(10)
        ] + [
            {"character_name": "B", "text": "2", "dialogue_index": i + 10}
            for i in range(5)
        ]
        batches = sc.group_dialogues_by_character(dialogues)
        total = sum(len(b["dialogues"]) for b in batches)
        assert total == 15
        print("PASS: All dialogues preserved")


# ============================================================
# PAYLOAD BUILDER
# ============================================================

class TestCharacterBatchPayload:
    """Test _build_character_batch_payload."""

    def test_single_speaker_format(self):
        """Payload uses single-speaker voiceConfig (not multiSpeaker)."""
        dialogues = [
            {"character_name": "Devang", "text": "Hello", "dialogue_index": 0},
            {"character_name": "Devang", "text": "How are you", "dialogue_index": 1},
        ]
        payload = sc._build_character_batch_payload(dialogues, "Schedar", {0: "", 1: ""})

        config = payload["generationConfig"]["speechConfig"]
        assert "voiceConfig" in config, "Should use single-speaker voiceConfig"
        assert "multiSpeakerVoiceConfig" not in config
        assert config["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Schedar"
        print("PASS: Uses single-speaker voiceConfig")

    def test_break_tags_between_dialogues(self):
        """Break tags inserted between dialogues, not after last."""
        dialogues = [
            {"character_name": "Devang", "text": "Hello", "dialogue_index": 0},
            {"character_name": "Devang", "text": "How are you", "dialogue_index": 1},
            {"character_name": "Devang", "text": "Goodbye", "dialogue_index": 2},
        ]
        payload = sc._build_character_batch_payload(dialogues, "Schedar", {0: "", 1: "", 2: ""})
        text = payload["contents"][0]["parts"][0]["text"]

        break_count = text.count('<break time="700ms"/>')
        assert break_count == 2, f"Expected 2 breaks, got {break_count}"

        lines = text.split("\n\n")
        assert '<break' not in lines[-1], "Last line should not have break tag"
        print("PASS: Break tags between dialogues")

    def test_punctuation_enforced(self):
        """Text without punctuation gets a period."""
        dialogues = [
            {"character_name": "A", "text": "Hello there", "dialogue_index": 0},
        ]
        payload = sc._build_character_batch_payload(dialogues, "Kore", {0: ""})
        text = payload["contents"][0]["parts"][0]["text"]
        assert "Hello there." in text
        print("PASS: Punctuation enforced")

    def test_director_notes_included(self):
        """Director notes appear in the text."""
        dialogues = [
            {"character_name": "A", "text": "Hello", "dialogue_index": 0},
        ]
        payload = sc._build_character_batch_payload(dialogues, "Kore", {0: "whispering"})
        text = payload["contents"][0]["parts"][0]["text"]
        assert "[whispering]" in text
        print("PASS: Director notes included")


# ============================================================
# TEXT NORMALIZATION & SIMILARITY
# ============================================================

class TestTextNormalization:
    """Test _normalize_to_tokens, _normalize_word, _words_similar."""

    def test_normalize_to_tokens_basic(self):
        tokens = sc._normalize_to_tokens("Hello, world!")
        assert tokens == ["hello", "world"]

    def test_normalize_to_tokens_unicode(self):
        tokens = sc._normalize_to_tokens("How are you?")
        assert tokens == ["how", "are", "you"]

    def test_normalize_word(self):
        assert sc._normalize_word("Hello,") == "hello"
        assert sc._normalize_word("world!") == "world"

    def test_words_similar_exact(self):
        assert sc._words_similar("hello", "hello") is True

    def test_words_similar_prefix(self):
        assert sc._words_similar("running", "run") is True

    def test_words_similar_different(self):
        assert sc._words_similar("hello", "world") is False

    def test_words_similar_empty(self):
        assert sc._words_similar("", "hello") is False
        assert sc._words_similar("hello", "") is False

    def test_words_similar_close(self):
        """Words with high character overlap match."""
        assert sc._words_similar("hello", "hallo") is True


# ============================================================
# TRANSCRIPTION ALIGNMENT
# ============================================================

class TestTranscriptionAlignment:
    """Test _align_transcription_with_dialogues."""

    def test_basic_alignment(self):
        """Two dialogues should align to correct word ranges."""
        words = [
            {"word": "Hello.", "start": 0.0, "end": 0.5, "confidence": 0.99},
            {"word": "Where", "start": 1.3, "end": 1.6, "confidence": 0.98},
            {"word": "were", "start": 1.6, "end": 1.8, "confidence": 0.97},
            {"word": "you?", "start": 1.8, "end": 2.1, "confidence": 0.99},
        ]
        dialogues = [
            {"text": "Hello.", "dialogue_index": 0},
            {"text": "Where were you?", "dialogue_index": 1},
        ]
        segments = sc._align_transcription_with_dialogues(words, dialogues, 3.0)

        assert len(segments) == 2
        assert segments[0] is not None
        assert segments[1] is not None

        # First dialogue should start near 0, end before second starts
        assert segments[0]["start"] < 0.5
        assert segments[0]["end"] < 1.5

        # Second dialogue should start after first ends
        assert segments[1]["start"] > 0.3
        assert segments[1]["end"] > 1.5
        assert segments[1]["end"] <= 3.0
        print(f"PASS: Basic alignment — seg0={segments[0]}, seg1={segments[1]}")

    def test_alignment_preserves_order(self):
        """Segments should be in temporal order."""
        words = [
            {"word": "First", "start": 0.0, "end": 0.5, "confidence": 0.9},
            {"word": "line.", "start": 0.5, "end": 1.0, "confidence": 0.9},
            {"word": "Second", "start": 1.5, "end": 2.0, "confidence": 0.9},
            {"word": "line.", "start": 2.0, "end": 2.5, "confidence": 0.9},
            {"word": "Third", "start": 3.0, "end": 3.5, "confidence": 0.9},
            {"word": "line.", "start": 3.5, "end": 4.0, "confidence": 0.9},
        ]
        dialogues = [
            {"text": "First line.", "dialogue_index": 0},
            {"text": "Second line.", "dialogue_index": 1},
            {"text": "Third line.", "dialogue_index": 2},
        ]
        segments = sc._align_transcription_with_dialogues(words, dialogues, 5.0)

        assert all(s is not None for s in segments)
        # Each segment should start after the previous one ends
        for i in range(1, len(segments)):
            assert segments[i]["start"] >= segments[i-1]["start"], \
                f"Segment {i} starts before segment {i-1}"
        print("PASS: Segments in temporal order")

    def test_alignment_respects_audio_duration(self):
        """No segment should exceed audio_duration."""
        words = [
            {"word": "Hello.", "start": 0.0, "end": 0.5, "confidence": 0.9},
        ]
        dialogues = [
            {"text": "Hello.", "dialogue_index": 0},
        ]
        segments = sc._align_transcription_with_dialogues(words, dialogues, 1.0)

        assert segments[0] is not None
        assert segments[0]["end"] <= 1.0
        print("PASS: Segment respects audio duration")

    def test_alignment_with_no_words(self):
        """Empty words list → all None."""
        dialogues = [{"text": "Hello.", "dialogue_index": 0}]
        segments = sc._align_transcription_with_dialogues([], dialogues, 1.0)
        assert segments == [None]

    def test_alignment_with_no_dialogues(self):
        """Empty dialogues → empty result."""
        words = [{"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.9}]
        segments = sc._align_transcription_with_dialogues(words, [], 1.0)
        assert segments == []

    def test_alignment_with_fuzzy_match(self):
        """Should handle minor word differences between dialogue and transcription."""
        words = [
            {"word": "Im", "start": 0.0, "end": 0.3, "confidence": 0.8},
            {"word": "fine.", "start": 0.3, "end": 0.6, "confidence": 0.9},
        ]
        dialogues = [
            {"text": "I'm fine.", "dialogue_index": 0},
        ]
        segments = sc._align_transcription_with_dialogues(words, dialogues, 1.0)
        # "im" should match "im" (from "i'm" normalized)
        assert segments[0] is not None, "Fuzzy match should work for 'I'm' → 'Im'"
        print("PASS: Fuzzy alignment works")

    def test_gap_midpoint_boundaries(self):
        """Adjacent dialogues should split at the midpoint of their gap."""
        words = [
            {"word": "Hello.", "start": 0.0, "end": 0.5, "confidence": 0.9},
            # Gap: 0.5 to 1.5 (1 second gap from break tag)
            {"word": "Goodbye.", "start": 1.5, "end": 2.0, "confidence": 0.9},
        ]
        dialogues = [
            {"text": "Hello.", "dialogue_index": 0},
            {"text": "Goodbye.", "dialogue_index": 1},
        ]
        segments = sc._align_transcription_with_dialogues(words, dialogues, 3.0)

        assert segments[0] is not None
        assert segments[1] is not None

        # Gap midpoint: (0.5 + 1.5) / 2 = 1.0
        # First segment should end at ~1.0
        assert abs(segments[0]["end"] - 1.0) < 0.01, \
            f"First segment end should be ~1.0, got {segments[0]['end']}"
        # Second segment should start at ~1.0
        assert abs(segments[1]["start"] - 1.0) < 0.01, \
            f"Second segment start should be ~1.0, got {segments[1]['start']}"
        print(f"PASS: Gap midpoint boundaries — gap split at {segments[0]['end']}")


# ============================================================
# ENSURE PUNCTUATION (regression)
# ============================================================

class TestEnsurePunctuation:
    def test_adds_period(self):
        assert sc._ensure_punctuation("Hello") == "Hello."

    def test_preserves_period(self):
        assert sc._ensure_punctuation("Hello.") == "Hello."

    def test_preserves_exclamation(self):
        assert sc._ensure_punctuation("Hello!") == "Hello!"

    def test_preserves_question(self):
        assert sc._ensure_punctuation("Hello?") == "Hello?"

    def test_empty(self):
        assert sc._ensure_punctuation("") == ""


# ============================================================
# WAV UTILITIES (regression)
# ============================================================

class TestWavUtilities:
    def _make_wav(self, duration=1.0, sr=24000):
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(b'\x00\x00' * int(duration * sr))
        return buf.getvalue()

    def test_validate_wav_good(self):
        wav = self._make_wav(1.0)
        assert sc._validate_wav(wav, "test") is True

    def test_validate_wav_too_small(self):
        assert sc._validate_wav(b"RIFF" + b"\x00" * 50 + b"WAVE", "test") is False

    def test_extract_clip(self):
        wav = self._make_wav(3.0)
        clip = sc._extract_clip_from_wav(wav, 1.0, 2.0)
        assert len(clip) > 0
        buf = io.BytesIO(clip)
        with wave.open(buf, 'rb') as wf:
            dur = wf.getnframes() / wf.getframerate()
            assert 0.9 <= dur <= 1.1

    def test_get_wav_duration(self):
        wav = self._make_wav(2.5)
        dur = sc._get_wav_duration(wav)
        assert 2.4 <= dur <= 2.6


# ============================================================
# CACHE (regression)
# ============================================================

class TestCacheKey:
    def test_deterministic(self):
        k1 = sc.compute_cache_key("Hello", "Kore", "")
        k2 = sc.compute_cache_key("Hello", "Kore", "")
        assert k1 == k2

    def test_different_inputs_different_keys(self):
        k1 = sc.compute_cache_key("Hello", "Kore", "")
        k2 = sc.compute_cache_key("Hello", "Schedar", "")
        assert k1 != k2

    def test_strips_whitespace(self):
        k1 = sc.compute_cache_key("  Hello  ", " Kore ", " notes ")
        k2 = sc.compute_cache_key("Hello", "Kore", "notes")
        assert k1 == k2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
