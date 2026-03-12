"""
Unit tests for pipeline Issue 1 (Deepgram empty utterances) and Issue 2 (incorrect batching).

Issue 1: Gemini payload must include punctuation + <break time="700ms"/> between dialogue turns.
Issue 2: Batching must use conversation-block detection, not forward-looking pair detection.
"""
import sys
sys.path.insert(0, '/app/backend')

import pytest
import script_compiler as sc


# ============================================================
# ISSUE 2 — BATCHING (conversation-block detection)
# ============================================================

class TestConversationBlockBatching:
    """Test group_dialogues_by_speaker_pairs with conversation-block algorithm."""

    def test_4_speakers_2_clear_blocks_produces_2_batches(self):
        """
        Script: Devang+Priya block, then Jyoti+Rohan block.
        Expected: 2 batches.
        """
        dialogues = [
            {"character_name": "Devang", "text": "Hello.", "dialogue_index": 0},
            {"character_name": "Priya", "text": "Hi.", "dialogue_index": 1},
            {"character_name": "Devang", "text": "Where were you?", "dialogue_index": 2},
            {"character_name": "Priya", "text": "I was waiting.", "dialogue_index": 3},
            {"character_name": "Jyoti", "text": "Hey Rohan.", "dialogue_index": 4},
            {"character_name": "Rohan", "text": "Hey Jyoti.", "dialogue_index": 5},
        ]
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

        dp_batch = next((b for b in batches if set(b["speakers"]) == {"Devang", "Priya"}), None)
        jr_batch = next((b for b in batches if set(b["speakers"]) == {"Jyoti", "Rohan"}), None)

        assert dp_batch is not None, "Devang+Priya batch missing"
        assert jr_batch is not None, "Jyoti+Rohan batch missing"
        assert len(dp_batch["dialogues"]) == 4
        assert len(jr_batch["dialogues"]) == 2
        print("PASS: 4 speakers, 2 clear blocks → 2 batches")

    def test_returning_speakers_merge_into_same_batch(self):
        """
        Script: Devang+Priya, Jyoti+Rohan, Devang+Priya again.
        The two Devang+Priya blocks should merge into 1 batch.
        """
        dialogues = [
            {"character_name": "Devang", "text": "Hello.", "dialogue_index": 0},
            {"character_name": "Priya", "text": "Hi.", "dialogue_index": 1},
            {"character_name": "Devang", "text": "How are you?", "dialogue_index": 2},
            {"character_name": "Priya", "text": "Good.", "dialogue_index": 3},
            {"character_name": "Jyoti", "text": "Hey.", "dialogue_index": 4},
            {"character_name": "Rohan", "text": "Sup.", "dialogue_index": 5},
            {"character_name": "Devang", "text": "Back again.", "dialogue_index": 6},
            {"character_name": "Priya", "text": "Welcome back.", "dialogue_index": 7},
        ]
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

        dp_batch = next((b for b in batches if set(b["speakers"]) == {"Devang", "Priya"}), None)
        jr_batch = next((b for b in batches if set(b["speakers"]) == {"Jyoti", "Rohan"}), None)

        assert dp_batch is not None
        assert jr_batch is not None
        assert len(dp_batch["dialogues"]) == 6, f"Expected 6, got {len(dp_batch['dialogues'])}"
        assert len(jr_batch["dialogues"]) == 2

        dp_indices = {d["dialogue_index"] for d in dp_batch["dialogues"]}
        assert dp_indices == {0, 1, 2, 3, 6, 7}, f"Wrong indices: {dp_indices}"
        print("PASS: Returning speakers merge into same batch (6+2)")

    def test_single_speaker_solo_batch(self):
        """All dialogues from one speaker → 1 batch with 1 speaker."""
        dialogues = [
            {"character_name": "Narrator", "text": "Once upon a time.", "dialogue_index": 0},
            {"character_name": "Narrator", "text": "The end.", "dialogue_index": 1},
        ]
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 1
        assert batches[0]["speakers"] == ["Narrator"]
        assert len(batches[0]["dialogues"]) == 2
        print("PASS: Single speaker → 1 solo batch")

    def test_two_speakers_alternating_one_batch(self):
        """Two speakers alternating → 1 batch."""
        dialogues = [
            {"character_name": "Hero", "text": "Fight!", "dialogue_index": 0},
            {"character_name": "Villain", "text": "Never!", "dialogue_index": 1},
            {"character_name": "Hero", "text": "Then die.", "dialogue_index": 2},
            {"character_name": "Villain", "text": "You first.", "dialogue_index": 3},
        ]
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)

        assert len(batches) == 1
        assert set(batches[0]["speakers"]) == {"Hero", "Villain"}
        assert len(batches[0]["dialogues"]) == 4
        print("PASS: 2 speakers alternating → 1 batch")

    def test_empty_dialogues(self):
        """Empty input → empty output."""
        assert sc.group_dialogues_by_speaker_pairs([]) == []
        print("PASS: Empty dialogues → empty batches")

    def test_pair_key_is_deterministic(self):
        """pair_key = sorted(A, B) regardless of who speaks first."""
        dialogues_ab = [
            {"character_name": "A", "text": "Hi.", "dialogue_index": 0},
            {"character_name": "B", "text": "Hey.", "dialogue_index": 1},
        ]
        dialogues_ba = [
            {"character_name": "B", "text": "Hey.", "dialogue_index": 0},
            {"character_name": "A", "text": "Hi.", "dialogue_index": 1},
        ]
        batches_ab = sc.group_dialogues_by_speaker_pairs(dialogues_ab)
        batches_ba = sc.group_dialogues_by_speaker_pairs(dialogues_ba)

        assert batches_ab[0]["speakers"] == batches_ba[0]["speakers"], \
            f"Pair key not deterministic: {batches_ab[0]['speakers']} vs {batches_ba[0]['speakers']}"
        print("PASS: Pair key is deterministic (sorted)")

    def test_total_dialogues_preserved(self):
        """All dialogues must appear exactly once across all batches."""
        dialogues = [
            {"character_name": "A", "text": "1", "dialogue_index": 0},
            {"character_name": "B", "text": "2", "dialogue_index": 1},
            {"character_name": "C", "text": "3", "dialogue_index": 2},
            {"character_name": "D", "text": "4", "dialogue_index": 3},
            {"character_name": "A", "text": "5", "dialogue_index": 4},
            {"character_name": "B", "text": "6", "dialogue_index": 5},
        ]
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)

        total = sum(len(b["dialogues"]) for b in batches)
        assert total == 6, f"Expected 6 total dialogues, got {total}"

        all_indices = set()
        for b in batches:
            for d in b["dialogues"]:
                all_indices.add(d["dialogue_index"])
        assert all_indices == {0, 1, 2, 3, 4, 5}, f"Missing indices: {all_indices}"
        print("PASS: All dialogues preserved across batches")

    def test_max_2_speakers_per_batch(self):
        """No batch should have more than 2 speakers."""
        dialogues = [
            {"character_name": "A", "text": "1", "dialogue_index": 0},
            {"character_name": "B", "text": "2", "dialogue_index": 1},
            {"character_name": "C", "text": "3", "dialogue_index": 2},
            {"character_name": "D", "text": "4", "dialogue_index": 3},
            {"character_name": "E", "text": "5", "dialogue_index": 4},
            {"character_name": "F", "text": "6", "dialogue_index": 5},
        ]
        batches = sc.group_dialogues_by_speaker_pairs(dialogues)

        for b in batches:
            assert len(b["speakers"]) <= 2, \
                f"Batch has >2 speakers: {b['speakers']}"
        print("PASS: All batches have ≤ 2 speakers")


# ============================================================
# ISSUE 1 — PAUSE INSERTION (punctuation + break tags)
# ============================================================

class TestPauseInsertion:
    """Test _build_multi_speaker_payload inserts punctuation and <break> tags."""

    def test_break_tags_between_lines(self):
        """Each line except the last should end with <break time="700ms"/>."""
        batch = {
            "speakers": ["Devang", "Priya"],
            "dialogues": [
                {"character_name": "Devang", "text": "Hello", "dialogue_index": 0},
                {"character_name": "Priya", "text": "Hi", "dialogue_index": 1},
                {"character_name": "Devang", "text": "Where were you", "dialogue_index": 2},
                {"character_name": "Priya", "text": "I was waiting", "dialogue_index": 3},
            ]
        }
        voice_map = {"Devang": "Schedar", "Priya": "Kore"}
        director_notes_map = {0: "", 1: "", 2: "", 3: ""}

        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        text = payload["contents"][0]["parts"][0]["text"]

        # Count break tags — should be 3 (between 4 lines)
        break_count = text.count('<break time="700ms"/>')
        assert break_count == 3, f"Expected 3 break tags, got {break_count}. Text:\n{text}"

        # Last line should NOT have a break tag
        lines = text.split("\n\n")
        assert '<break' not in lines[-1], f"Last line should not have break tag: {lines[-1]}"
        print("PASS: Break tags inserted between all lines except last")

    def test_punctuation_enforced(self):
        """Lines without punctuation should get a period appended."""
        batch = {
            "speakers": ["A", "B"],
            "dialogues": [
                {"character_name": "A", "text": "Hello there", "dialogue_index": 0},
                {"character_name": "B", "text": "How are you", "dialogue_index": 1},
            ]
        }
        voice_map = {"A": "Kore", "B": "Schedar"}
        director_notes_map = {0: "", 1: ""}

        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        text = payload["contents"][0]["parts"][0]["text"]

        # "Hello there" should become "Hello there."
        assert "Hello there." in text, f"Punctuation not enforced: {text}"
        assert "How are you." in text, f"Punctuation not enforced: {text}"
        print("PASS: Punctuation enforced on lines without it")

    def test_existing_punctuation_preserved(self):
        """Lines that already end with punctuation should NOT get double punctuation."""
        batch = {
            "speakers": ["A", "B"],
            "dialogues": [
                {"character_name": "A", "text": "Hello!", "dialogue_index": 0},
                {"character_name": "B", "text": "How are you?", "dialogue_index": 1},
            ]
        }
        voice_map = {"A": "Kore", "B": "Schedar"}
        director_notes_map = {0: "", 1: ""}

        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        text = payload["contents"][0]["parts"][0]["text"]

        assert "Hello!." not in text, f"Double punctuation: {text}"
        assert "you?." not in text, f"Double punctuation: {text}"
        assert "Hello!" in text
        assert "How are you?" in text
        print("PASS: Existing punctuation preserved (no doubling)")

    def test_director_notes_with_break_tags(self):
        """Director notes + break tags should coexist."""
        batch = {
            "speakers": ["A", "B"],
            "dialogues": [
                {"character_name": "A", "text": "Listen", "dialogue_index": 0},
                {"character_name": "B", "text": "Okay", "dialogue_index": 1},
            ]
        }
        voice_map = {"A": "Kore", "B": "Schedar"}
        director_notes_map = {0: "whispering", 1: ""}

        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        text = payload["contents"][0]["parts"][0]["text"]

        assert "[whispering]" in text
        assert '<break time="700ms"/>' in text
        # Notes should be before the text, break after
        assert "Listen." in text
        print("PASS: Director notes + break tags coexist correctly")

    def test_single_dialogue_no_break_tag(self):
        """A batch with only 1 dialogue should have no break tag."""
        batch = {
            "speakers": ["A", "B"],
            "dialogues": [
                {"character_name": "A", "text": "Solo line", "dialogue_index": 0},
            ]
        }
        voice_map = {"A": "Kore", "B": "Schedar"}
        director_notes_map = {0: ""}

        payload = sc._build_multi_speaker_payload(batch, voice_map, director_notes_map)
        text = payload["contents"][0]["parts"][0]["text"]

        assert '<break' not in text, f"Single dialogue should have no break tag: {text}"
        assert "Solo line." in text
        print("PASS: Single dialogue has no break tag")


class TestEnsurePunctuation:
    """Test _ensure_punctuation helper."""

    def test_adds_period_to_plain_text(self):
        assert sc._ensure_punctuation("Hello") == "Hello."

    def test_preserves_period(self):
        assert sc._ensure_punctuation("Hello.") == "Hello."

    def test_preserves_exclamation(self):
        assert sc._ensure_punctuation("Hello!") == "Hello!"

    def test_preserves_question(self):
        assert sc._ensure_punctuation("Hello?") == "Hello?"

    def test_preserves_semicolon(self):
        assert sc._ensure_punctuation("Hello;") == "Hello;"

    def test_preserves_colon(self):
        assert sc._ensure_punctuation("Hello:") == "Hello:"

    def test_strips_whitespace(self):
        assert sc._ensure_punctuation("  Hello  ") == "Hello."

    def test_empty_string(self):
        assert sc._ensure_punctuation("") == ""


# ============================================================
# REGRESSION: Reconcile utterances still works
# ============================================================

class TestReconcileUtterancesRegression:
    """Ensure _reconcile_utterances still works after changes."""

    def test_exact_match_passthrough(self):
        utterances = [
            {"speaker": 0, "start": 0.0, "end": 1.0, "transcript": "A"},
            {"speaker": 1, "start": 1.0, "end": 2.0, "transcript": "B"},
        ]
        result = sc._reconcile_utterances(utterances, 2, "test")
        assert result == utterances

    def test_merge_same_speaker(self):
        utterances = [
            {"speaker": 0, "start": 0.0, "end": 1.0, "transcript": "A"},
            {"speaker": 0, "start": 1.0, "end": 2.0, "transcript": "B"},
            {"speaker": 1, "start": 2.0, "end": 3.0, "transcript": "C"},
        ]
        result = sc._reconcile_utterances(utterances, 2, "test")
        assert len(result) == 2
        assert result[0]["end"] == 2.0

    def test_equal_division_fallback(self):
        utterances = [
            {"speaker": 0, "start": 0.0, "end": 5.0, "transcript": "All"},
        ]
        result = sc._reconcile_utterances(utterances, 4, "test", audio_duration=10.0)
        assert len(result) == 4
        # All timestamps should be within audio duration
        for u in result:
            assert u["end"] <= 10.0, f"Timestamp exceeds audio duration: {u['end']}"
        print("PASS: Equal division respects audio duration boundary")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
