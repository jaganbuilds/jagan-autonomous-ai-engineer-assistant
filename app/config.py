from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    gemini_api_key: str = ""
    debug: bool = True
    jagan_ai_owner_id: str = "default_owner"
    
    # Memory Configuration
    memory_low_importance_age_days: int = 30
    memory_normal_importance_age_days: int = 90
    memory_high_importance_age_days: int = 365
    max_memory_context_items: int = 5
    max_memory_context_chars: int = 2000
    
    # Semantic Memory Configuration
    memory_semantic_retrieval_enabled: bool = True
    memory_semantic_model: str = "all-MiniLM-L6-v2"
    memory_semantic_threshold: float = 0.3
    memory_semantic_weight: float = 1.0
    memory_keyword_weight: float = 1.0
    memory_importance_weight: float = 0.5
    memory_recency_weight: float = 0.1
    enable_arbeitnow: bool = True
    enable_adzuna: bool = False
    enable_remotive: bool = False
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "gb"
    
    # Voice Configuration
    voice_enabled: bool = False
    stt_provider: str = "none"
    tts_provider: str = "none"
    default_voice_language: str = "en"
    
    # Local STT Configuration (faster-whisper)
    stt_model_size: str = "tiny"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_max_audio_seconds: int = 120
    stt_max_audio_mb: int = 10
    stt_upload_dir: str = "temp_audio"
    
    # Local TTS Configuration (pyttsx3)
    tts_output_dir: str = "data/voice_output"
    tts_model: str = "pyttsx3_default"
    tts_max_text_length: int = 5000
    
    # Microphone Configuration
    microphone_enabled: bool = True
    microphone_sample_rate: int = 16000
    microphone_channels: int = 1
    microphone_max_duration_seconds: int = 60
    microphone_temp_dir: str = "data/temp_audio"
    
    # GitHub Configuration
    github_token: str = ""
    github_api_base_url: str = "https://api.github.com"
    github_repository_limit: int = 30
    github_file_limit: int = 50
    github_commit_limit: int = 10
    
    # Workspace Configuration
    workspace_root: str = "."
    workspace_max_read_bytes: int = 102400 # 100KB default limit
    

    # Execution Configuration
    workspace_execution_timeout_seconds: int = 30
    workspace_execution_max_output_bytes: int = 50000
    
    # Reads from .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

@lru_cache()
def get_settings():
    return Settings()
