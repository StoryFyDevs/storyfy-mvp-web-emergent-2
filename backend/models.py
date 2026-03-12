from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum

# User roles
UserRole = Literal["admin", "creator", "listener"]

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: UserRole = "creator"
    status: str = "active"
    limits_remaining: int = 1000
    audition_credits: int = 500
    storage_used_mb: float = 0.0
    storage_limit_mb: float = 500.0
    created_at: datetime

class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: UserRole = "creator"
    status: str = "active"
    limits_remaining: int = 1000
    audition_credits: int = 500
    storage_used_mb: float = 0.0
    storage_limit_mb: float = 500.0
    created_at: datetime

# ============ ADMIN MODELS ============

class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class LimitTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    transaction_id: str
    user_id: str
    amount: int
    balance_after: int
    transaction_type: str
    description: str
    reference_id: Optional[str] = None
    admin_id: Optional[str] = None
    created_at: datetime

class AdminAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_id: str
    admin_id: str
    action_type: str
    target_type: str
    target_id: str
    details: Dict[str, Any]
    created_at: datetime

class GenerationLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    generation_id: str
    user_id: str
    story_id: Optional[str] = None
    episode_id: Optional[str] = None
    generation_type: str
    duration_seconds: float
    limits_used: int
    data_size_bytes: int
    status: str
    error_message: Optional[str] = None
    model_used: str
    created_at: datetime

class LimitAdjustRequest(BaseModel):
    user_id: str
    amount: int
    reason: str

class UserStatusUpdate(BaseModel):
    user_id: str
    status: str
    reason: Optional[str] = None

class SystemStats(BaseModel):
    total_users: int
    total_creators: int
    active_creators_7d: int
    active_creators_30d: int
    total_stories: int
    total_episodes: int
    total_audio_minutes: float
    total_limits_consumed: int
    total_storage_mb: float

class SessionData(BaseModel):
    session_id: str

# ============ STORY & EPISODE MODELS ============

class StoryCreate(BaseModel):
    title: str
    genre: str
    language: str
    description: str
    story_type: str
    cover_art_url: Optional[str] = None

class Story(BaseModel):
    model_config = ConfigDict(extra="ignore")
    story_id: str
    user_id: str
    title: str
    genre: str
    language: str
    description: str
    story_type: str
    cover_art_url: Optional[str] = None
    status: str = "draft"
    publishedAt: Optional[datetime] = None
    play_count: int = 0
    created_at: datetime
    updated_at: datetime

class EpisodeCreate(BaseModel):
    story_id: str
    title: str
    order: int
    script: Optional[str] = ""

class Episode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    episode_id: str
    story_id: str
    title: str
    order: int
    status: str
    script: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    project_state: Optional[Dict[str, Any]] = None
    isPublished: bool = False
    publishedAt: Optional[datetime] = None
    finalAudioUrl: Optional[str] = None
    play_count: int = 0
    created_at: datetime
    updated_at: datetime

class CharacterCreate(BaseModel):
    story_id: str
    name: str
    voice_id: Optional[str] = None
    voice_settings: Optional[Dict[str, Any]] = None

class Character(BaseModel):
    model_config = ConfigDict(extra="ignore")
    character_id: str
    story_id: str
    name: str
    voice_id: Optional[str] = None
    voice_settings: Optional[Dict[str, Any]] = None
    created_at: datetime

# ============ TTS MODELS ============

class TTSRequest(BaseModel):
    text: str
    voice_id: str
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    speed: float = 1.0
    use_speaker_boost: bool = True
    output_format: str = "mp3_44100_128"
    language_code: Optional[str] = None
    style_preset: Optional[str] = None
    style_instructions: Optional[str] = None

    @property
    def validated_stability(self) -> float:
        valid_values = [0.0, 0.5, 1.0]
        return min(valid_values, key=lambda x: abs(x - self.stability))

class TTSResponse(BaseModel):
    audio_url: str
    text: str
    voice_id: str
    duration_seconds: Optional[float] = None
    settings_used: Optional[dict] = None

class DialogueSpeaker(BaseModel):
    text: str
    voice_id: str

class DialogueRequest(BaseModel):
    inputs: List[DialogueSpeaker]
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    speed: float = 1.0
    output_format: str = "mp3_44100_128"

    @property
    def validated_stability(self) -> float:
        valid_values = [0.0, 0.5, 1.0]
        return min(valid_values, key=lambda x: abs(x - self.stability))

class DialogueResponse(BaseModel):
    audio_url: str
    speakers_count: int
    total_turns: int

class AudioAssetCreate(BaseModel):
    story_id: str
    episode_id: Optional[str] = None
    asset_type: str
    name: str
    file_path: str
    duration: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class AudioAsset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    asset_id: str
    user_id: str
    story_id: str
    episode_id: Optional[str] = None
    asset_type: str
    name: str
    file_path: str
    duration: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

# ============ MOBILE / LISTENER MODELS ============

class ListenerSignup(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = ""

class ListenerLogin(BaseModel):
    email: EmailStr
    password: str

class ProgressSave(BaseModel):
    episode_id: str
    current_time: float
    duration: Optional[float] = None

class PlayEventCreate(BaseModel):
    episode_id: str
    event_type: str = "play"
    position_seconds: Optional[float] = 0

class LibrarySave(BaseModel):
    story_id: str
