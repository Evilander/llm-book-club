from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    app_env: str = Field("dev", alias="APP_ENV")
    auth_secret: str = Field("dev-auth-secret-change-me", alias="AUTH_SECRET")
    frontend_app_url: str = Field("http://localhost:3000", alias="FRONTEND_APP_URL")
    app_session_cookie_name: str = Field("llm_book_session", alias="APP_SESSION_COOKIE_NAME")
    app_session_ttl_hours: int = Field(24 * 30, alias="APP_SESSION_TTL_HOURS")

    llm_provider: str = Field("openai", alias="LLM_PROVIDER")
    chatgpt_codex_binary: str = Field("codex", alias="CHATGPT_CODEX_BINARY")
    chatgpt_state_dir: str = Field(".readagain/chatgpt", alias="CHATGPT_STATE_DIR")
    chatgpt_model: str | None = Field(None, alias="CHATGPT_MODEL")
    chatgpt_turn_timeout_seconds: int = Field(90, ge=10, le=300, alias="CHATGPT_TURN_TIMEOUT_SECONDS")
    chatgpt_max_output_chars: int = Field(24000, ge=1000, le=100000, alias="CHATGPT_MAX_OUTPUT_CHARS")
    chatgpt_max_input_chars: int = Field(250000, ge=1000, le=1000000, alias="CHATGPT_MAX_INPUT_CHARS")
    openai_auth_mode: str = Field("api_key", alias="OPENAI_AUTH_MODE")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    anthropic_auth_mode: str = Field("api_key", alias="ANTHROPIC_AUTH_MODE")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    gemini_auth_mode: str = Field("api_key", alias="GEMINI_AUTH_MODE")
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.0-flash", alias="GEMINI_MODEL")
    google_oauth_client_id: str | None = Field(None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(None, alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: str | None = Field(None, alias="GOOGLE_OAUTH_REDIRECT_URI")
    google_oauth_project_id: str | None = Field(None, alias="GOOGLE_OAUTH_PROJECT_ID")
    google_oauth_scopes: str = Field(
        "openid email profile https://www.googleapis.com/auth/cloud-platform",
        alias="GOOGLE_OAUTH_SCOPES",
    )
    grok_api_key: str | None = Field(None, alias="GROK_API_KEY")
    grok_model: str = Field("grok-3", alias="GROK_MODEL")
    local_llm_model: str = Field("llama3.2", alias="LOCAL_LLM_MODEL", min_length=1, max_length=200, pattern=r"^\S+$")
    local_llm_base_url: str | None = Field(None, alias="LOCAL_LLM_BASE_URL")

    embeddings_provider: str = Field("local", alias="EMBEDDINGS_PROVIDER")
    openai_embeddings_model: str = Field("text-embedding-3-large", alias="OPENAI_EMBEDDINGS_MODEL")
    local_embeddings_base_url: str | None = Field(None, alias="LOCAL_EMBEDDINGS_BASE_URL")
    local_embeddings_model: str = Field("Qwen/Qwen3-Embedding-0.6B", alias="LOCAL_EMBEDDINGS_MODEL")
    local_embeddings_revision: str | None = Field(None, alias="LOCAL_EMBEDDINGS_REVISION")
    local_embeddings_dimension: int = Field(1024, ge=1, le=3072, alias="LOCAL_EMBEDDINGS_DIMENSION")
    local_embeddings_device: str = Field("cpu", alias="LOCAL_EMBEDDINGS_DEVICE")
    local_embeddings_cache_dir: str = Field(".readagain/models", alias="LOCAL_EMBEDDINGS_CACHE_DIR")
    local_embeddings_max_tokens: int = Field(2048, ge=128, le=8192, alias="LOCAL_EMBEDDINGS_MAX_TOKENS")
    local_embeddings_threads: int = Field(4, ge=1, le=32, alias="LOCAL_EMBEDDINGS_THREADS")
    local_embeddings_query_prompt: str | None = Field(None, alias="LOCAL_EMBEDDINGS_QUERY_PROMPT")
    local_embeddings_document_prompt: str = Field("", alias="LOCAL_EMBEDDINGS_DOCUMENT_PROMPT")

    reranker_provider: str = Field("none", alias="RERANKER_PROVIDER")  # none|cohere|local
    reranker_model: str = Field("rerank-v3.5", alias="RERANKER_MODEL")
    cohere_api_key: str | None = Field(None, alias="COHERE_API_KEY")
    local_reranker_model: str = Field("BAAI/bge-reranker-v2-m3", alias="LOCAL_RERANKER_MODEL")

    tts_provider: str = Field("vibevoice", alias="TTS_PROVIDER")
    tts_base_url: str | None = Field(None, alias="TTS_BASE_URL")
    tts_model: str = Field("tts-1", alias="TTS_MODEL")
    elevenlabs_api_key: str | None = Field(None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(None, alias="ELEVENLABS_VOICE_ID")

    embedding_cache_ttl: int = Field(3600, alias="EMBEDDING_CACHE_TTL")

    max_upload_mb: int = Field(200, alias="MAX_UPLOAD_MB")
    local_ingest_max_mb: int = Field(0, alias="LOCAL_INGEST_MAX_MB")
    library_scan_cache_ttl_sec: int = Field(300, alias="LIBRARY_SCAN_CACHE_TTL_SEC")

    # Local books directory for filesystem browsing
    books_dir: str | None = Field(None, alias="BOOKS_DIR")
    audiobooks_dir: str | None = Field(None, alias="AUDIOBOOKS_DIR")

    cors_origins: str = Field("http://localhost:3000", alias="CORS_ORIGINS")  # comma-separated
    rate_limit_default: str = Field("60/minute", alias="RATE_LIMIT_DEFAULT")

    # --- Token budget guardrails ---
    # Maximum number of conversation history messages sent to the LLM per turn.
    # The system prompt is always included; this limits user/assistant messages.
    max_history_messages: int = Field(50, alias="MAX_HISTORY_MESSAGES")

    # Maximum estimated tokens of retrieved evidence context injected per agent call.
    # Evidence chunks are trimmed (oldest dropped) if the total exceeds this budget.
    max_context_tokens: int = Field(4000, alias="MAX_CONTEXT_TOKENS")

    # Maximum tokens requested from the LLM per single agent response.
    max_tokens_per_turn: int = Field(2048, alias="MAX_TOKENS_PER_TURN")

    # Maximum number of messages allowed in a single discussion session.
    # Once reached, the session should be closed or a new one started.
    max_session_messages: int = Field(200, alias="MAX_SESSION_MESSAGES")

settings = Settings()
