from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    openai_api_key: str = ''
    openai_model: str = 'gpt-4.1'
    reasoning_effort: str = 'low'
    openai_tracing_enabled: bool = False
    embedding_model: str = 'text-embedding-3-small'
    database_path: str = str(ROOT / 'data/surveillance.sqlite3')
    max_tool_calls: int = 24
    max_job_seconds: int = 360
    runtime_path: str = str(ROOT / 'data/agent.sqlite3')
    source_path: str = str(ROOT / 'data/population.sqlite3')
    analyst_email: str = ''
    notification_from: str = 'surveillance@demo.local'
    smtp_host: str = ''
    smtp_port: int = 1025
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_starttls: bool = False
    app_url: str = 'http://127.0.0.1:8767'
    worker_concurrency: int = 4
    investigation_archive: str = str(ROOT / 'data/investigation_archive')
    transcription_model: str = 'whisper-1'
    analysis_artifacts: str = str(ROOT / 'data/analysis_artifacts')
    escalation_artifacts: str = str(ROOT / 'output/pdf/escalations')
    surveillance_manager_email: str = ''


settings = Settings()


def reasoning_options():
    """Explicit low-effort reasoning for Sol; other model overrides keep their contract."""
    return {'reasoning': {'effort': settings.reasoning_effort, 'summary': 'auto'}} if settings.openai_model == 'gpt-6.1-sol' else {}

def output_budget(visible_tokens):
    # Responses counts reasoning tokens within the output limit.
    return visible_tokens + 4096 if settings.openai_model == 'gpt-6.1-sol' else visible_tokens
