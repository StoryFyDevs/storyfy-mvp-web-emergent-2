"""
Script Compiler — Character-based batched audio generation pipeline.

Pipeline:
1. Group dialogues by character (one Gemini call per character)
2. For each character batch: Gemini single-speaker TTS → combined audio
3. Send combined audio to Deepgram → word-level transcription
4. Align transcription words with original dialogue texts → segment boundaries
5. Slice combined audio at aligned boundaries → individual clips
6. Validate, upload, cache each clip
7. FALLBACK: if alignment fails → per-dialogue generation

Preserves dialogue_index throughout for exact script-order reconstruction
in the Audio Studio.
"""
import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import re
import time
import uuid
import wave
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

import supabase_db as ndb
import supabase_storage as storage
import generation_queue as gq
import storage_cleanup as sc_storage

logger = logging.getLogger("script_compiler")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
MAX_RETRIES = 3
REGEN_TIMEOUT = 90  # Maximum seconds for single dialogue regeneration
BATCH_GEMINI_RETRIES = 1  # retries for batch Gemini calls before fallback
MIN_AUDIO_BYTES = 1000
MIN_AUDIO_DURATION = 0.3  # minimum seconds for valid audio
BREAK_TAG_MS = 700  # pause duration in ms between dialogue turns (600-800ms range)

# Cost estimation (configurable)
GEMINI_COST_PER_CALL = 0.01   # USD
DEEPGRAM_COST_PER_MIN = 0.007  # USD

_active_jobs: Dict[str, str] = {}
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=180.0)
    return _http_client


# ──────────────────────────────────────────────
#  DEBUG LOGGING
# ──────────────────────────────────────────────

async def _debug_log(generation_id: str, creator_id: str, episode_id: str,
                     event_type: str, message: str, metadata: Dict = None):
    """Write a debug log entry for the generation run."""
    try:
        await ndb.insert_one("generation_debug_logs", {
            "log_id": f"log_{uuid.uuid4().hex[:12]}",
            "generation_id": generation_id,
            "creator_id": creator_id,
            "episode_id": episode_id,
            "event_type": event_type,
            "message": message,
            "metadata": json.dumps(metadata or {}),
        })
    except Exception as e:
        logger.warning(f"Debug log write failed: {e}")


# ──────────────────────────────────────────────
#  CACHE
# ──────────────────────────────────────────────

def compute_cache_key(text: str, voice_id: str, notes: str = "") -> str:
    raw = f"{text.strip()}|{voice_id.strip()}|{notes.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _is_stale_url(url: str) -> bool:
    """Return True for any dead storage URL that will 404.

    Stale patterns:
      - https://*.nhost.run/...  → old Nhost HTTP URLs (service no longer active)
      - https://*.nhost.io/...   → old Nhost HTTP URLs
      - nhost-file:<UUID>        (bare UUID, no slash) → old Nhost-era ref with no Supabase path
    Valid patterns:
      - bucket/path              → canonical Supabase storage format
      - nhost-file:bucket/path   → legacy prefix wrapping a valid Supabase bucket/path
      - data:audio/wav;base64,...→ embedded audio
    """
    if not url:
        return False
    if "nhost.run" in url or "nhost.io" in url:
        return True
    if url.startswith("nhost-file:"):
        file_id = url[len("nhost-file:"):]
        return "/" not in file_id
    return False


async def check_cache(cache_key: str) -> Optional[Dict]:
    try:
        row = await ndb.find_one("audio_cache", {"cache_key": cache_key})
        if row and row.get("audio_url"):
            audio_url = row["audio_url"]
            if _is_stale_url(audio_url):
                logger.info(f"Cache hit for {cache_key} has stale URL — treating as miss")
                return None
            asyncio.create_task(sc_storage.touch_clip(audio_url))
            return {"audio_url": audio_url, "duration_seconds": row.get("duration_seconds", 0), "cached": True}
    except Exception as e:
        logger.warning(f"Cache lookup error: {e}")
    return None


async def store_cache(cache_key: str, voice_id: str, text: str, notes: str, audio_url: str, duration: float):
    try:
        await ndb.upsert_one("audio_cache", {
            "cache_key": cache_key, "voice_id": voice_id, "dialogue_text": text,
            "director_notes": notes or "", "audio_url": audio_url, "duration_seconds": duration,
        }, conflict_columns=["cache_key"], update_columns=["audio_url", "duration_seconds"])
        asyncio.create_task(sc_storage.touch_clip(audio_url))
        file_id = sc_storage._extract_file_id(audio_url)
        if file_id:
            try:
                await ndb.update_rows("audio_clips", {"file_id": file_id}, {"is_cached": True, "cache_key": cache_key})
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Cache store error: {e}")


# ──────────────────────────────────────────────
#  AUDIO UTILITIES
# ──────────────────────────────────────────────

def _pcm_to_wav(pcm: bytes, sr: int = 24000, ch: int = 1, sw: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(sw)
        wf.setframerate(sr)
        wf.writeframes(pcm)
    out = buf.getvalue()
    buf.close()
    return out


def _validate_wav(wav: bytes, label: str) -> bool:
    if not wav or len(wav) < MIN_AUDIO_BYTES:
        logger.error(f"[{label}] WAV too small: {len(wav) if wav else 0}B")
        return False
    if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        logger.error(f"[{label}] Invalid WAV header")
        return False
    return True


def _get_wav_duration(wav_bytes: bytes) -> float:
    """Get duration in seconds from WAV bytes."""
    try:
        src = io.BytesIO(wav_bytes)
        with wave.open(src, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _extract_clip_from_wav(wav_bytes: bytes, start_sec: float, end_sec: float) -> bytes:
    """Extract a clip from WAV audio at exact timestamps. Returns new WAV bytes."""
    src = io.BytesIO(wav_bytes)
    with wave.open(src, "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        total_frames = wf.getnframes()

        start_frame = max(0, int(start_sec * sr))
        end_frame = min(total_frames, int(end_sec * sr))
        if end_frame <= start_frame:
            return b""

        wf.setpos(start_frame)
        frames = wf.readframes(end_frame - start_frame)

    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(sw)
        wf.setframerate(sr)
        wf.writeframes(frames)
    clip = out.getvalue()
    out.close()
    return clip


async def _upload_wav(wav: bytes, filename: str, episode_id: str = "") -> str:
    try:
        path = f"scripts/{episode_id}/{filename}" if episode_id else f"scripts/{filename}"
        meta = await storage.upload_file(path, wav, "audio/wav")
        fid = meta.get("id", "")
        if fid:
            logger.info(f"Uploaded {filename}: file_id={fid}, size={len(wav)}B")
            return fid
    except Exception as e:
        logger.warning(f"Upload failed for {filename}, falling back to base64: {e}")
    return f"data:audio/wav;base64,{base64.b64encode(wav).decode()}"


# ──────────────────────────────────────────────
#  CHARACTER BATCHING
# ──────────────────────────────────────────────

def group_dialogues_by_character(dialogues: List[Dict]) -> List[Dict]:
    """Group dialogues by character name.

    Each character gets one batch → one Gemini call.

    Returns [{character: str, dialogues: [dict, ...]}]
    """
    if not dialogues:
        return []

    batches: Dict[str, Dict] = {}
    for d in dialogues:
        char = d.get("character_name", "Narrator")
        if char not in batches:
            batches[char] = {"character": char, "dialogues": []}
        batches[char]["dialogues"].append(d)

    result = list(batches.values())

    logger.info(f"Character batching: {len(dialogues)} dialogues → {len(result)} character batch(es)")
    for b in result:
        indices = [d.get("dialogue_index", "?") for d in b["dialogues"]]
        logger.info(f"  [{b['character']}]: {len(b['dialogues'])} dialogues (indices: {indices})")

    return result


# ──────────────────────────────────────────────
#  GEMINI TTS (character batch & single-dialogue)
# ──────────────────────────────────────────────

def _ensure_punctuation(text: str) -> str:
    """Ensure dialogue text ends with punctuation for clearer TTS boundaries."""
    text = text.strip()
    if text and text[-1] not in '.!?;:':
        text += '.'
    return text


def _build_character_batch_payload(dialogues: List[Dict], voice_id: str,
                                   director_notes_map: Dict[int, str]) -> Dict:
    """Build a single-speaker Gemini payload for a character's dialogue batch.

    Concatenates all dialogues with break tags between them.
    Each dialogue ends with punctuation for clearer TTS boundaries.
    """
    lines = []
    for i, d in enumerate(dialogues):
        text = _ensure_punctuation(d.get("text", "").strip())
        idx = d.get("dialogue_index", 0)
        notes = director_notes_map.get(idx, "")

        if notes:
            line = f"[{notes}] {text}"
        else:
            line = text

        # Add break between dialogues (not after last)
        if i < len(dialogues) - 1:
            line += f' <break time="{BREAK_TAG_MS}ms"/>'

        lines.append(line)

    full_text = "\n\n".join(lines)

    return {
        "contents": [{"parts": [{"text": full_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}
            }
        }
    }


def _build_single_speaker_payload(text: str, voice_id: str, notes: str = "") -> Dict:
    if notes and notes.strip():
        full_text = f"[Director Notes: {notes.strip()}]\n\n{text}"
    else:
        full_text = text
    return {
        "contents": [{"parts": [{"text": full_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}
            }
        }
    }


async def _call_gemini_tts(payload: Dict, label: str = "") -> Tuple[bytes, float]:
    """Call Gemini TTS. Returns (pcm_bytes, duration_seconds).

    Handles multi-part responses by concatenating all audio parts.
    Validates that the returned audio meets minimum size/duration requirements.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"
    client = _get_http_client()
    logger.info(f"[{label}] Gemini TTS request...")
    resp = await client.post(url, json=payload)
    if resp.status_code == 429:
        raise Exception("Voice service busy — please retry shortly.")
    if resp.status_code != 200:
        raise Exception(f"Gemini TTS {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise Exception("Empty Gemini response: no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise Exception("Empty Gemini response: no parts")

    # Concatenate audio from ALL parts (Gemini may split long audio)
    pcm_chunks = []
    for pi, part in enumerate(parts):
        b64 = part.get("inlineData", {}).get("data", "")
        if b64:
            chunk = base64.b64decode(b64)
            pcm_chunks.append(chunk)
            logger.debug(f"[{label}] Part {pi}: {len(chunk)}B PCM")

    if not pcm_chunks:
        raise Exception("No audio data in Gemini response (all parts empty)")

    pcm = b"".join(pcm_chunks)
    dur = len(pcm) / (24000 * 2)  # 24kHz, 16-bit mono

    if len(pcm) < MIN_AUDIO_BYTES:
        raise Exception(f"Gemini audio too small: {len(pcm)}B (min {MIN_AUDIO_BYTES}B)")

    if dur < MIN_AUDIO_DURATION:
        raise Exception(f"Gemini audio too short: {dur:.2f}s (min {MIN_AUDIO_DURATION}s)")

    logger.info(f"[{label}] Gemini returned {len(pcm)}B PCM ({len(pcm_chunks)} part(s)), {dur:.2f}s")
    return pcm, dur


# ──────────────────────────────────────────────
#  DEEPGRAM TRANSCRIPTION (word-level timestamps)
# ──────────────────────────────────────────────

async def _call_deepgram_transcription(wav_bytes: bytes, label: str = "") -> Optional[List[Dict]]:
    """Send WAV to Deepgram and return word-level timestamps.

    Each word: {word: str, start: float, end: float, confidence: float}
    Returns None on failure.
    """
    if not DEEPGRAM_API_KEY:
        logger.warning("DEEPGRAM_API_KEY not set — skipping transcription")
        return None

    client = _get_http_client()
    url = "https://api.deepgram.com/v1/listen"
    params = {
        "model": "nova-3",
        "punctuate": "true",
        "smart_format": "true",
        "detect_language": "true",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav",
    }

    try:
        logger.info(f"[{label}] Deepgram transcription request ({len(wav_bytes)}B)...")
        resp = await client.post(url, params=params, headers=headers, content=wav_bytes)
        if resp.status_code != 200:
            logger.error(f"[{label}] Deepgram error {resp.status_code}: {resp.text[:300]}")
            return None

        data = resp.json()
        channels = data.get("results", {}).get("channels", [])
        if not channels:
            return None

        alt = channels[0].get("alternatives", [])
        if not alt:
            return None

        words_raw = alt[0].get("words", [])
        words = []
        for w in words_raw:
            words.append({
                "word": w.get("word", ""),
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
                "confidence": w.get("confidence", 0.0),
            })

        transcript = alt[0].get("transcript", "")
        logger.info(f"[{label}] Deepgram returned {len(words)} words, transcript: {transcript[:100]}...")
        return words

    except Exception as e:
        logger.error(f"[{label}] Deepgram transcription failed: {e}")
        return None


# ──────────────────────────────────────────────
#  TEXT ALIGNMENT (transcription → dialogue boundaries)
# ──────────────────────────────────────────────

_PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)


def _normalize_to_tokens(text: str) -> List[str]:
    """Normalize text into lowercase tokens for alignment matching."""
    cleaned = _PUNCT_RE.sub('', text.lower())
    return cleaned.split()


def _normalize_word(word: str) -> str:
    """Normalize a single Deepgram word for comparison."""
    return _PUNCT_RE.sub('', word.lower())


def _words_similar(a: str, b: str) -> bool:
    """Check if two normalized words are similar enough for alignment."""
    if a == b:
        return True
    if not a or not b:
        return False
    # One starts with the other (handles contractions, plurals)
    if len(a) >= 3 and len(b) >= 3:
        if a.startswith(b) or b.startswith(a):
            return True
    # Character overlap ratio for words of similar length
    if abs(len(a) - len(b)) <= 2:
        common = sum(1 for ca, cb in zip(a, b) if ca == cb)
        max_len = max(len(a), len(b))
        if max_len > 0 and common / max_len >= 0.7:
            return True
    return False


def _align_transcription_with_dialogues(
    words: List[Dict], dialogues: List[Dict], audio_duration: float
) -> List[Optional[Dict]]:
    """Align Deepgram word-level timestamps with original dialogue texts.

    For each dialogue, finds the matching word range in the transcription
    by sequential greedy matching. Then computes segment boundaries using
    gap midpoints between adjacent dialogues.

    Returns list of {start, end, matched_ratio} dicts (or None for failures).
    """
    n = len(dialogues)
    if not words or not dialogues:
        return [None] * n

    # Step 1: Tokenize each dialogue
    dialogue_tokens = [_normalize_to_tokens(d.get("text", "")) for d in dialogues]

    # Step 2: Sequential word-range matching
    word_ranges: List[Optional[Tuple[int, int]]] = []
    current_word_idx = 0

    for di, tokens in enumerate(dialogue_tokens):
        if not tokens or current_word_idx >= len(words):
            word_ranges.append(None)
            continue

        first_match = None
        last_match = None
        token_idx = 0
        scan_idx = current_word_idx

        # Scan Deepgram words to match dialogue tokens sequentially
        while scan_idx < len(words) and token_idx < len(tokens):
            dg_norm = _normalize_word(words[scan_idx]["word"])
            expected = tokens[token_idx]

            if _words_similar(dg_norm, expected):
                if first_match is None:
                    first_match = scan_idx
                last_match = scan_idx
                token_idx += 1
                scan_idx += 1
            else:
                # Allow skipping an unmatched Deepgram word (filler, extra)
                scan_idx += 1
                # But don't scan too far ahead — limit lookahead
                if first_match is not None and scan_idx > last_match + 5:
                    break
                if first_match is None and scan_idx > current_word_idx + len(tokens) * 3:
                    break

        if first_match is not None and last_match is not None:
            matched_count = token_idx  # how many dialogue tokens were matched
            word_ranges.append((first_match, last_match))
            current_word_idx = last_match + 1
            logger.debug(
                f"  Dialogue {di}: matched {matched_count}/{len(tokens)} tokens, "
                f"words [{first_match}:{last_match}]")
        else:
            word_ranges.append(None)
            logger.debug(f"  Dialogue {di}: no match found")

    # Step 3: Convert word ranges to timestamps with gap-based boundaries
    segments: List[Optional[Dict]] = []
    for di in range(n):
        wr = word_ranges[di]
        if wr is None:
            segments.append(None)
            continue

        start_idx, end_idx = wr
        word_start = words[start_idx]["start"]
        word_end = words[end_idx]["end"]

        # Determine segment start: midpoint of gap with previous dialogue
        if di > 0 and word_ranges[di - 1] is not None:
            prev_end_idx = word_ranges[di - 1][1]
            prev_end_time = words[prev_end_idx]["end"]
            seg_start = (prev_end_time + word_start) / 2
        else:
            # First dialogue (or no previous match) — start from 0 or word start
            seg_start = max(0, word_start - 0.15)

        # Determine segment end: midpoint of gap with next dialogue
        if di < n - 1 and word_ranges[di + 1] is not None:
            next_start_idx = word_ranges[di + 1][0]
            next_start_time = words[next_start_idx]["start"]
            seg_end = (word_end + next_start_time) / 2
        else:
            # Last dialogue (or no next match) — extend to audio end or word end
            seg_end = min(audio_duration, word_end + 0.15)

        # Clamp boundaries
        seg_start = max(0, seg_start)
        seg_end = min(audio_duration, seg_end)

        matched_ratio = (end_idx - start_idx + 1) / max(len(dialogue_tokens[di]), 1)

        segments.append({
            "start": round(seg_start, 3),
            "end": round(seg_end, 3),
            "matched_ratio": round(matched_ratio, 2),
        })

    matched_count = sum(1 for s in segments if s is not None)
    logger.info(f"Alignment result: {matched_count}/{n} dialogues aligned")
    return segments


# ──────────────────────────────────────────────
#  CHARACTER BATCH GENERATION PIPELINE
# ──────────────────────────────────────────────

async def _generate_character_batch(
    character: str, dialogues: List[Dict], voice_id: str,
    episode_id: str, user_id: str,
    director_notes_map: Dict[int, str],
    job_id: str = "", metrics: Dict = None,
    story_id: str = "",
) -> List[Dict]:
    """Generate audio for all dialogues of a single character.

    Pipeline: Gemini (single-speaker) → Deepgram (transcription) → align → extract clips.
    Falls back to per-dialogue generation on any failure.
    """
    n = len(dialogues)
    if metrics is None:
        metrics = {}

    # Single dialogue — generate directly, no alignment needed
    if n == 1:
        logger.info(f"[{character}] Single dialogue — direct generation")
        d = dialogues[0]
        voice_map = {character: voice_id}
        return await _fallback_per_dialogue(dialogues, voice_map, episode_id, user_id, director_notes_map, job_id, story_id=story_id)

    logger.info(f"[{character}] Generating batch: {n} dialogues, voice={voice_id}")
    await _debug_log(job_id, user_id, episode_id, "BATCH_CREATED",
                     f"Character [{character}]: {n} dialogues, voice={voice_id}",
                     {"character": character, "dialogue_count": n, "voice_id": voice_id,
                      "dialogue_indexes": [d.get("dialogue_index", 0) for d in dialogues]})

    try:
        # ── Pre-flight checks ──
        total_chars = sum(len(d.get("text", "")) for d in dialogues)
        rate_check = await gq.check_rate_limits(user_id, total_chars)
        if not rate_check.get("allowed"):
            await asyncio.sleep(30)
            rate_check = await gq.check_rate_limits(user_id, total_chars)
            if not rate_check.get("allowed"):
                raise Exception(rate_check.get("reason", "Rate limit exceeded"))

        # ── Step 1: Build payload and call Gemini (with retry) ──
        payload = _build_character_batch_payload(dialogues, voice_id, director_notes_map)

        await _debug_log(job_id, user_id, episode_id, "GEMINI_REQUEST_SENT",
                         f"Character [{character}]: {n} dialogues, {total_chars} chars",
                         {"character": character, "dialogue_count": n, "total_chars": total_chars})

        pcm = None
        total_dur = 0.0
        gemini_count = 0
        last_err = None

        for attempt in range(1, BATCH_GEMINI_RETRIES + 2):
            gemini_count += 1
            try:
                pcm, total_dur = await _call_gemini_tts(payload, f"{character}/attempt-{attempt}")
                last_err = None
                break
            except Exception as e:
                last_err = e
                is_empty = "Empty Gemini" in str(e) or "No audio" in str(e) or "too small" in str(e)
                if is_empty:
                    metrics["empty_gemini_responses"] = metrics.get("empty_gemini_responses", 0) + 1
                if attempt <= BATCH_GEMINI_RETRIES:
                    metrics["gemini_retries"] = metrics.get("gemini_retries", 0) + 1
                    await _debug_log(job_id, user_id, episode_id, "GEMINI_RETRY",
                                     f"Character [{character}]: attempt {attempt} failed ({e}), retrying...",
                                     {"attempt": attempt, "error": str(e)})
                    await asyncio.sleep(3)

        if last_err is not None:
            raise Exception(f"Gemini failed after {gemini_count} attempts: {last_err}")

        # ── Validate audio ──
        wav = _pcm_to_wav(pcm)
        if not _validate_wav(wav, character):
            raise Exception("Combined WAV validation failed")

        await _debug_log(job_id, user_id, episode_id, "GEMINI_RESPONSE_RECEIVED",
                         f"Character [{character}]: {len(wav)}B WAV, {total_dur:.2f}s",
                         {"audio_size_bytes": len(wav), "duration_seconds": round(total_dur, 2),
                          "gemini_requests": gemini_count})

        if total_dur < MIN_AUDIO_DURATION:
            raise Exception(f"Audio too short for segmentation: {total_dur:.2f}s")

        await gq.record_generation(user_id, success=True, tokens_used=total_chars)

        # ── Step 2: Deepgram transcription ──
        await _debug_log(job_id, user_id, episode_id, "DEEPGRAM_TRANSCRIPTION_STARTED",
                         f"Character [{character}]: Sending {len(wav)}B ({total_dur:.2f}s) to Deepgram",
                         {"audio_size_bytes": len(wav), "duration_seconds": round(total_dur, 2)})

        words = await _call_deepgram_transcription(wav, character)
        if words is None or len(words) == 0:
            await _debug_log(job_id, user_id, episode_id, "DEEPGRAM_NO_WORDS",
                             f"Character [{character}]: Deepgram returned no words",
                             {"character": character})
            raise Exception("Deepgram returned no words")

        await _debug_log(job_id, user_id, episode_id, "DEEPGRAM_WORDS_RECEIVED",
                         f"Character [{character}]: {len(words)} words transcribed",
                         {"word_count": len(words),
                          "sample_words": [w["word"] for w in words[:10]]})

        # ── Step 3: Align transcription with dialogues ──
        segments = _align_transcription_with_dialogues(words, dialogues, total_dur)

        aligned_count = sum(1 for s in segments if s is not None)
        await _debug_log(job_id, user_id, episode_id, "ALIGNMENT_RESULT",
                         f"Character [{character}]: {aligned_count}/{n} dialogues aligned",
                         {"aligned": aligned_count, "total": n,
                          "segments": [s for s in segments if s is not None]})

        if aligned_count == 0:
            raise Exception("Transcription alignment failed — no dialogues matched")

        # ── Step 4: Extract clips ──
        results = []
        for i, d in enumerate(dialogues):
            idx = d.get("dialogue_index", 0)
            char_safe = character.replace(" ", "_")
            dialogue_id = f"{char_safe}_{idx + 1:02d}"

            if segments[i] is None:
                # Alignment failed for this dialogue — per-dialogue fallback
                logger.warning(f"[{dialogue_id}] Alignment failed — per-dialogue fallback")
                await _debug_log(job_id, user_id, episode_id, "CLIP_ALIGNMENT_FALLBACK",
                                 f"[{dialogue_id}] No alignment, generating individually",
                                 {"dialogue_index": idx})
                try:
                    fb = await _generate_single_dialogue(d, voice_id, episode_id)
                    await gq.record_generation(user_id, success=True, tokens_used=len(d.get("text", "")))
                    results.append(fb)
                except Exception as e:
                    results.append({
                        "dialogue_index": idx, "audio_url": "", "duration_seconds": 0,
                        "error": str(e), "cached": False,
                        "character_name": character, "generated_voice_id": voice_id,
                    })
                continue

            seg = segments[i]
            clip_wav = _extract_clip_from_wav(wav, seg["start"], seg["end"])

            if not _validate_wav(clip_wav, dialogue_id):
                logger.warning(f"[{dialogue_id}] Extracted clip invalid — per-dialogue fallback")
                try:
                    fb = await _generate_single_dialogue(d, voice_id, episode_id)
                    results.append(fb)
                except Exception as e:
                    results.append({
                        "dialogue_index": idx, "audio_url": "", "duration_seconds": 0,
                        "error": str(e), "cached": False,
                        "character_name": character, "generated_voice_id": voice_id,
                    })
                continue

            clip_dur = seg["end"] - seg["start"]
            filename = f"{dialogue_id}.wav"
            audio_url = await _upload_wav(clip_wav, filename, episode_id)
            asyncio.create_task(sc_storage.register_clip(
                audio_url=audio_url, episode_id=episode_id, story_id=story_id,
                dialogue_index=idx, voice_id=voice_id, is_cached=False,
            ))

            await _debug_log(job_id, user_id, episode_id, "CLIP_EXTRACTION",
                             f"[{dialogue_id}] {seg['start']:.2f}s—{seg['end']:.2f}s, "
                             f"{len(clip_wav)}B, {clip_dur:.2f}s, match={seg['matched_ratio']:.0%}",
                             {"dialogue_index": idx, "character": character,
                              "start": seg["start"], "end": seg["end"],
                              "clip_size_bytes": len(clip_wav),
                              "duration": round(clip_dur, 2),
                              "matched_ratio": seg["matched_ratio"]})

            results.append({
                "dialogue_index": idx,
                "audio_url": audio_url,
                "duration_seconds": round(clip_dur, 2),
                "filename": filename,
                "character_name": character,
                "audio_size_bytes": len(clip_wav),
                "generated_voice_id": voice_id,
                "cached": False,
                "batch_generated": True,
            })

        logger.info(f"[{character}] Batch complete: {len(results)} clips, {gemini_count} Gemini request(s)")
        return results

    except Exception as e:
        logger.warning(f"[{character}] Batch pipeline failed: {e} — falling back to per-dialogue")
        await _debug_log(job_id, user_id, episode_id, "FALLBACK_TRIGGERED",
                         f"Character [{character}]: {e}",
                         {"character": character, "dialogue_count": n, "error": str(e)})
        await gq.record_generation(user_id, success=False, tokens_used=0)
        voice_map = {character: voice_id}
        return await _fallback_per_dialogue(dialogues, voice_map, episode_id, user_id, director_notes_map, job_id, story_id=story_id)


# ──────────────────────────────────────────────
#  FALLBACK: PER-DIALOGUE GENERATION
# ──────────────────────────────────────────────

async def _generate_single_dialogue(d: Dict, voice_id: str, episode_id: str, story_id: str = "") -> Dict:
    """Generate audio for one dialogue (retry-capable)."""
    text = d.get("text", "")
    notes = d.get("director_notes", "")
    char_name = d.get("character_name", "Narrator").replace(" ", "_")
    idx = d.get("dialogue_index", 0)
    dialogue_id = f"{char_name}_{idx + 1:02d}"

    logger.info(f"[{dialogue_id}] Per-dialogue generation: voice={voice_id}, text_len={len(text)}")

    payload = _build_single_speaker_payload(text, voice_id, notes)
    last_err = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pcm, dur = await _call_gemini_tts(payload, dialogue_id)
            wav = _pcm_to_wav(pcm)
            if not _validate_wav(wav, dialogue_id):
                raise Exception(f"WAV validation failed: {len(wav)}B")

            filename = f"{dialogue_id}.wav"
            audio_url = await _upload_wav(wav, filename, episode_id)
            asyncio.create_task(sc_storage.register_clip(
                audio_url=audio_url, episode_id=episode_id, story_id=story_id,
                dialogue_index=idx, voice_id=voice_id, is_cached=False,
            ))

            return {
                "dialogue_index": idx,
                "audio_url": audio_url,
                "duration_seconds": round(dur, 2),
                "filename": filename,
                "character_name": d.get("character_name", "Narrator"),
                "audio_size_bytes": len(wav),
                "generated_voice_id": voice_id,
                "cached": False,
                "batch_generated": False,
            }
        except Exception as e:
            last_err = e
            logger.warning(f"[{dialogue_id}] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(3)

    raise Exception(f"[{dialogue_id}] Failed after {MAX_RETRIES} attempts: {last_err}")


async def _fallback_per_dialogue(dialogues: List[Dict], voice_map: Dict[str, str],
                                 episode_id: str, user_id: str,
                                 director_notes_map: Dict[int, str],
                                 job_id: str = "", story_id: str = "") -> List[Dict]:
    """Generate each dialogue individually (fallback path)."""
    results = []
    for i, d in enumerate(dialogues):
        voice_id = voice_map.get(d.get("character_name", "Narrator"), "Kore")
        idx = d.get("dialogue_index", 0)

        rate_check = await gq.check_rate_limits(user_id, len(d.get("text", "")))
        if not rate_check.get("allowed"):
            await asyncio.sleep(30)

        try:
            r = await _generate_single_dialogue(d, voice_id, episode_id, story_id=story_id)
            await gq.record_generation(user_id, success=True, tokens_used=len(d.get("text", "")))
            results.append(r)
        except Exception as e:
            logger.error(f"Fallback failed for dialogue {idx}: {e}")
            await gq.record_generation(user_id, success=False, tokens_used=0)
            results.append({
                "dialogue_index": idx, "audio_url": "", "duration_seconds": 0,
                "error": str(e), "cached": False,
                "character_name": d.get("character_name", ""),
                "generated_voice_id": voice_id,
            })

        if i < len(dialogues) - 1:
            await asyncio.sleep(2)

    return results


# ──────────────────────────────────────────────
#  MAIN JOB RUNNER
# ──────────────────────────────────────────────

async def run_generation_job(job_id: str, episode_id: str, user_id: str,
                             dialogues: List[Dict], voice_map: Dict[str, str],
                             story_id: str = ""):
    """Background task: generate audio for an entire script.

    1. Check cache for every dialogue
    2. Group uncached dialogues into character batches
    3. Generate each batch (single-speaker TTS + Deepgram transcription + alignment)
    4. Cache results
    5. Finalize job with all results including dialogue_index
    """
    # Prevent concurrent jobs for same episode
    if episode_id in _active_jobs:
        old = _active_jobs[episode_id]
        logger.warning(f"Episode {episode_id} already has job {old} — cancelling it")
        try:
            await ndb.update_rows("script_generation_jobs", {"job_id": old}, {
                "status": "cancelled", "error_message": "Superseded",
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
        except Exception:
            pass
    _active_jobs[episode_id] = job_id

    try:
        logger.info(f"Job {job_id}: {len(dialogues)} dialogues for episode {episode_id}")
        await ndb.update_rows("script_generation_jobs", {"job_id": job_id}, {
            "status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()
        })
        await _debug_log(job_id, user_id, episode_id, "SCRIPT_COMPILE",
                         f"Starting generation: {len(dialogues)} dialogues",
                         {"dialogue_count": len(dialogues), "characters": list(voice_map.keys())})

        start_time = time.time()
        results: Dict[int, Dict] = {}
        to_generate: List[Dict] = []
        director_notes_map: Dict[int, str] = {}
        cache_hits = 0
        cache_misses = 0

        # ── Step 1: Cache check ──
        for d in dialogues:
            idx = d.get("dialogue_index", d.get("index", 0))
            d["dialogue_index"] = idx
            voice_id = voice_map.get(d.get("character_name", "Narrator"), "Kore")
            notes = d.get("director_notes", "")
            director_notes_map[idx] = notes
            ck = compute_cache_key(d["text"], voice_id, notes)

            cached = await check_cache(ck)
            if cached:
                char_name = d.get("character_name", "Narrator").replace(" ", "_")
                logger.info(f"[{char_name}_{idx+1:02d}] Cache HIT")
                results[idx] = {
                    **cached, "character_name": d.get("character_name", ""),
                    "dialogue_index": idx, "filename": f"{char_name}_{idx+1:02d}.wav",
                    "generated_voice_id": voice_id,
                }
                cache_hits += 1
                await _update_progress(job_id, len(results), len(dialogues))
            else:
                d["cache_key"] = ck
                to_generate.append(d)
                cache_misses += 1

        if not to_generate:
            logger.info(f"Job {job_id}: All {len(dialogues)} dialogues from cache")
            await _finish_job(job_id, results, len(dialogues))
            return

        logger.info(f"Job {job_id}: {len(results)} cached, {len(to_generate)} to generate")

        # ── Step 2: Group into character batches ──
        char_batches = group_dialogues_by_character(to_generate)
        logger.info(f"Job {job_id}: {len(to_generate)} dialogues → {len(char_batches)} character batch(es)")

        await _debug_log(job_id, user_id, episode_id, "BATCHING_COMPLETE",
                         f"{len(to_generate)} dialogues → {len(char_batches)} character batches",
                         {"batch_count": len(char_batches),
                          "batches": [{
                              "character": b["character"],
                              "dialogue_count": len(b["dialogues"]),
                          } for b in char_batches]})

        # Shared metrics dict
        job_metrics = {"empty_gemini_responses": 0, "gemini_retries": 0}

        # ── Step 3: Generate each character batch sequentially ──
        for bi, batch in enumerate(char_batches):
            if _active_jobs.get(episode_id) != job_id:
                logger.warning(f"Job {job_id} cancelled")
                return

            character = batch["character"]
            char_voice = voice_map.get(character, "Kore")

            batch_results = await _generate_character_batch(
                character, batch["dialogues"], char_voice,
                episode_id, user_id, director_notes_map,
                job_id, metrics=job_metrics, story_id=story_id)

            for r in batch_results:
                idx = r["dialogue_index"]
                results[idx] = r

                # Cache successful results
                if r.get("audio_url") and not r.get("error"):
                    d_match = next((d for d in to_generate if d.get("dialogue_index") == idx), None)
                    if d_match and d_match.get("cache_key"):
                        await store_cache(
                            d_match["cache_key"],
                            voice_map.get(r.get("character_name", ""), "Kore"),
                            d_match.get("text", ""),
                            d_match.get("director_notes", ""),
                            r["audio_url"], r["duration_seconds"]
                        )

                await _update_progress(job_id, len(results), len(dialogues))

            # Inter-batch delay for rate limits
            if bi < len(char_batches) - 1:
                await asyncio.sleep(2)

        # ── Step 4: Finalize ──
        await _finish_job(job_id, results, len(dialogues))
        gen_time = time.time() - start_time
        gemini_batch_calls = sum(1 for b in char_batches if len(b["dialogues"]) > 1)
        fallback_calls = sum(1 for r in results.values() if not r.get("batch_generated") and not r.get("cached"))
        total_gemini_calls = gemini_batch_calls + fallback_calls
        gemini_calls_saved = len(to_generate) - total_gemini_calls
        total_audio_dur = sum(r.get("duration_seconds", 0) for r in results.values())
        deepgram_minutes = total_audio_dur / 60.0 if gemini_batch_calls > 0 else 0
        seg_success = 100.0 if gemini_batch_calls > 0 and fallback_calls == 0 else (
            (1 - fallback_calls / max(len(to_generate), 1)) * 100)
        est_cost = total_gemini_calls * GEMINI_COST_PER_CALL + deepgram_minutes * DEEPGRAM_COST_PER_MIN

        # Write metrics
        try:
            await ndb.insert_one("generation_metrics", {
                "generation_id": job_id,
                "creator_id": user_id,
                "story_id": "",
                "episode_id": episode_id,
                "dialogue_count": len(dialogues),
                "speaker_pair_count": len(char_batches),
                "gemini_calls_used": total_gemini_calls,
                "gemini_calls_saved": max(0, gemini_calls_saved),
                "batch_count": len(char_batches),
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "deepgram_audio_minutes": round(deepgram_minutes, 3),
                "segmentation_success_rate": round(seg_success, 1),
                "fallback_triggered": fallback_calls > 0,
                "generation_time_seconds": round(gen_time, 2),
                "estimated_cost": round(est_cost, 4),
                "empty_gemini_responses": job_metrics.get("empty_gemini_responses", 0),
                "gemini_retries": job_metrics.get("gemini_retries", 0),
            })
        except Exception as me:
            logger.warning(f"Metrics write failed: {me}")

        logger.info(
            f"Job {job_id}: FINISHED — "
            f"{len(results)} clips, "
            f"{gemini_batch_calls} batch call(s), "
            f"{fallback_calls} fallback call(s), "
            f"{cache_hits} cache hit(s), "
            f"cost=${est_cost:.4f}, "
            f"time={gen_time:.1f}s"
        )

    except Exception as e:
        logger.error(f"Job {job_id} FAILED: {e}")
        await ndb.update_rows("script_generation_jobs", {"job_id": job_id}, {
            "status": "failed", "error_message": str(e)[:500],
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    finally:
        if _active_jobs.get(episode_id) == job_id:
            del _active_jobs[episode_id]


async def regenerate_single_dialogue(
    episode_id: str,
    story_id: str,
    dialogue: Dict,
    voice_id: str,
    user_id: str,
) -> Dict:
    """Generate a fresh clip for one dialogue, bypassing the cache entirely.
    Marks the old clip (same episode + dialogue_index) as inactive so storage
    cleanup can reclaim it after the grace period.
    Wraps the generation in a timeout to prevent gateway 502s."""
    rate = await gq.check_rate_limits(user_id, len(dialogue.get("text", "")))
    if not rate.get("allowed"):
        raise Exception(f"Rate limit exceeded: {rate.get('reason', 'try again later')}")

    try:
        result = await asyncio.wait_for(
            _generate_single_dialogue(dialogue, voice_id, episode_id, story_id=story_id),
            timeout=REGEN_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(f"[regen] Timeout after {REGEN_TIMEOUT}s for episode={episode_id}")
        raise Exception(f"Generation timed out after {REGEN_TIMEOUT}s. Please try again.")

    # Cache the new clip so future full-regenerations can reuse it
    text = dialogue.get("text", "")
    notes = dialogue.get("director_notes", "")
    cache_key = compute_cache_key(text, voice_id, notes)
    asyncio.create_task(
        store_cache(cache_key, voice_id, text, notes, result["audio_url"], result["duration_seconds"])
    )

    await gq.record_generation(user_id, success=True, tokens_used=len(text))
    return result


async def _update_progress(job_id: str, done: int, total: int):
    await ndb.update_rows("script_generation_jobs", {"job_id": job_id}, {
        "completed_dialogues": done, "updated_at": datetime.now(timezone.utc).isoformat()
    })


async def _finish_job(job_id: str, results: Dict, total: int):
    serializable = {str(k): v for k, v in results.items()}
    has_errors = any(v.get("error") for v in results.values())
    await ndb.update_rows("script_generation_jobs", {"job_id": job_id}, {
        "status": "completed" if not has_errors else "completed_with_errors",
        "completed_dialogues": total,
        "result_data": json.dumps(serializable),
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
