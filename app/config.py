from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    data_dir: Path = Path('data')
    ollama_base_url: str = ''
    ollama_model: str = 'qwen3.5-hermes:64k'
    num_ctx: int = 8192
    num_predict: int = 4096
    temperature: float = 0.1
    presence_penalty: float = 0
    think: bool = False
    rough_counts: bool = True
    verification: Literal['off','always'] = 'off'
    keep_alive: str = '30m'
    rows_per_band: int = Field(default=12,ge=1,le=12)
    connect_timeout: float = 15
    write_timeout: float = 300
    pool_timeout: float = 30
    read_timeout: float = 3600
    wall_timeout: float = Field(default=14400,ge=0)
    heartbeat_interval: float = 10
    retry_delays: str = '30,120,300,900,1800'
    disconnect_cooldown: float = 60
    max_files: int = 500
    max_expanded_bytes: int = 2_000_000_000
    max_file_bytes: int = 50_000_000
    max_response_bytes: int = 20_000_000
    max_pixels: int = 80_000_000
    libreoffice: str = ''
    pause_start: str = ''
    pause_end: str = ''

    def profile(self, smaller=False):
        return dict(num_ctx=min(8192,self.num_ctx) if smaller else self.num_ctx,
                    num_predict=self.num_predict * (2 if smaller else 1),
                    temperature=self.temperature, presence_penalty=self.presence_penalty)

    @property
    def delays(self):
        return [float(x) for x in self.retry_delays.split(',')]

settings = Settings()
