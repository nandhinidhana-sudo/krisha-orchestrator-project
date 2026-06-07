from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path = Path("app_data")
    upload_dir: Path = Path("app_data/uploads")
    extracted_dir: Path = Path("app_data/extracted")
    database_path: Path = Path("app_data/app.db")
    chunk_size_words: int = 320
    chunk_overlap_words: int = 60
    memory_turn_threshold: int = 10
    raw_message_window: int = 6
    retrieval_top_k: int = 8

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
