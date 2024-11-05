import os
from typing import List, Any, Dict, Tuple, Optional
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

def parse_allowed_hosts(v: Any) -> List[str]:
    if isinstance(v, str):
        return [host.strip() for host in v.split(',') if host.strip()]
    elif isinstance(v, list):
        return v
    return ["localhost", "127.0.0.1"]  # Default value

class EmojiConfig(BaseModel):
    emoji: str
    label: str
    message: str

def parse_emoji_config(v: Any) -> Dict[str, EmojiConfig]:
    if not v:
        return {
            "bookmark": EmojiConfig(
                emoji="bookmark",
                label="Read Later",
                message="Saved article to your reading list"
            )
        }
    
    try:
        # Format: emoji1:label1:message1;emoji2:label2:message2
        configs = {}
        for config_str in v.split(';'):
            if not config_str.strip():
                continue
            emoji, label, message = [part.strip() for part in config_str.split(':')]
            configs[emoji] = EmojiConfig(emoji=emoji, label=label, message=message)
        return configs
    except:
        return {
            "bookmark": EmojiConfig(
                emoji="bookmark",
                label="Read Later",
                message="Saved article to your reading list"
            )
        }

class EnvSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: str, field_info: Any) -> Tuple[Any, str, bool]:
        env_val = os.getenv(field)
        if env_val is not None:
            if field == "ALLOWED_HOSTS":
                return parse_allowed_hosts(env_val), field, True
            if field == "EMOJI_CONFIGS":
                return parse_emoji_config(env_val), field, True
            return env_val, field, True
        return None, field, False

    def prepare_field_value(self, field_name: str, field_value: Any, value_is_complex: bool) -> Any:
        return field_value

    def __call__(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for field, field_info in self.settings_cls.model_fields.items():
            field_value, field_key, value_set = self.get_field_value(field, field_info)
            if value_set:
                d[field_key] = self.prepare_field_value(field, field_value, False)
        return d

class Settings(BaseSettings):
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    PORT: int = Field(default=8000)
    SLACK_BOT_TOKEN: str = Field(default="default_token")
    SLACK_SIGNING_SECRET: str = Field(default="default_secret")
    READWISE_API_KEY: str = Field(default="default_api_key")
    DOCUMENT_TAG: str = Field(default="slack-import")  # Tag for imported documents
    RATE_LIMIT_PER_MINUTE: int = Field(default=20)
    LOG_LEVEL: str = Field(default="INFO")
    EMOJI_CONFIGS: Dict[str, EmojiConfig] = Field(
        default_factory=lambda: {
            "bookmark": EmojiConfig(
                emoji="bookmark",
                label="Read Later",
                message="Saved article to your reading list"
            )
        }
    )
    MINIMUM_ITEM_COUNT: int = Field(default=14)
    MAXIMUM_ITEM_COUNT: int = Field(default=20)  # Maximum number of articles to retrieve
    NUMBER_OF_LONG_ARTICLES: int = Field(default=4)
    NUMBER_OF_SHORT_ARTICLES: int = Field(default=5)
    MIN_DAYS_TO_CHECK: int = Field(default=14)
    MAXIMUM_DAYS_TO_CHECK: int = Field(default=30)

    @property
    def RATE_LIMIT(self) -> str:
        return f"{self.RATE_LIMIT_PER_MINUTE}/minute"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        file_secret_settings: Any,
        dotenv_settings: Any = None,
        **kwargs: Any
    ) -> Tuple[Any, ...]:
        return (EnvSettingsSource(settings_cls),)

settings = Settings()
