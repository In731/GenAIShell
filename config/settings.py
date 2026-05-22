import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """System-wide configuration settings loaded from environment variables and verified using Pydantic."""
    
    # API Settings
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", validation_alias="GEMINI_MODEL") # gemini-2.0-flash is the current stable model
    
    # Security Settings
    safe_mode_enabled: bool = Field(default=True, validation_alias="SAFE_MODE_ENABLED")
    max_shell_timeout: int = Field(default=30, validation_alias="MAX_SHELL_TIMEOUT")
    
    # Path Settings
    workspace_root: Path = Field(default_factory=lambda: Path(os.getcwd()).resolve())
    memory_db_path: Path = Field(default=Path("./data/memory.db"), validation_alias="MEMORY_DB_PATH")
    vector_db_path: Path = Field(default=Path("./data/vector_store.json"), validation_alias="VECTOR_DB_PATH")
    
    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: Path = Field(default=Path("./logs/assistant.log"))

    # Config source loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def model_post_init(self, __context) -> None:
        """Post-initialization to create directories for logs and database paths."""
        # Convert path representations to absolute forms
        self.memory_db_path = Path(self.memory_db_path).resolve()
        self.vector_db_path = Path(self.vector_db_path).resolve()
        self.log_file = Path(self.log_file).resolve()
        
        # Ensure directories exist
        self.memory_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

# Instantiate config globally
settings = Settings()
