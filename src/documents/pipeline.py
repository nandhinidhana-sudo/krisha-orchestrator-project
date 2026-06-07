import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from docx import Document
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import AppConfig
from src.storage.database import Database
from src.utils import clean_text, new_id


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    filename: str
    chunk_count: int


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    content: str
    score: float
    metadata: dict


class DocumentPipeline:
    def __init__(self, config: AppConfig, db: Database):
        self.config = config
        self.db = db

    def ingest_uploaded_file(self, session_id: str, uploaded_file: BinaryIO) -> IngestResult:
        filename = Path(uploaded_file.name).name
        file_type = Path(filename).suffix.lower().lstrip(".")
        safe_name = f"{new_id()}-{filename}"
        file_path = self.config.upload_dir / safe_name

        with file_path.open("wb") as target:
            shutil.copyfileobj(uploaded_file, target)

        document_id = self.db.add_document(session_id, filename, file_type, file_path)
        text = self.extract_text(file_path, file_type)
        extracted_path = self.config.extracted_dir / f"{document_id}.txt"
        extracted_path.write_text(text, encoding="utf-8")

        chunks = self.chunk_text(text)
        for index, chunk in enumerate(chunks):
            self.db.add_document_chunk(
                document_id=document_id,
                session_id=session_id,
                chunk_index=index,
                content=chunk,
                metadata={"filename": filename, "file_type": file_type},
            )

        self.db.update_document_processed(document_id, extracted_path, len(chunks))
        return IngestResult(document_id=document_id, filename=filename, chunk_count=len(chunks))

    def extract_text(self, file_path: Path, file_type: str) -> str:
        if file_type == "pdf":
            return self._extract_pdf(file_path)
        if file_type == "docx":
            return self._extract_docx(file_path)
        if file_type == "txt":
            return file_path.read_text(encoding="utf-8", errors="ignore")
        if file_type == "csv":
            return self._extract_table(pd.read_csv(file_path))
        if file_type == "xlsx":
            return self._extract_table(pd.read_excel(file_path))
        raise ValueError(f"Unsupported file type: {file_type}")

    def chunk_text(self, text: str) -> list[str]:
        words = clean_text(text).split()
        if not words:
            return []

        chunks = []
        step = max(1, self.config.chunk_size_words - self.config.chunk_overlap_words)
        for start in range(0, len(words), step):
            chunk_words = words[start : start + self.config.chunk_size_words]
            if chunk_words:
                chunks.append(" ".join(chunk_words))
        return chunks

    def retrieve(self, session_id: str, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        chunks = self.db.list_document_chunks(session_id)
        if not chunks:
            return []

        texts = [chunk["content"] for chunk in chunks]
        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        matrix = vectorizer.fit_transform(texts + [query])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)

        results = []
        for index, score in ranked[: top_k or self.config.retrieval_top_k]:
            if score <= 0:
                continue
            chunk = chunks[index]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["id"],
                    document_id=chunk["document_id"],
                    content=chunk["content"],
                    score=float(score),
                    metadata={"chunk_index": chunk["chunk_index"]},
                )
            )
        return results

    def _extract_pdf(self, file_path: Path) -> str:
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    def _extract_docx(self, file_path: Path) -> str:
        doc = Document(str(file_path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)

    def _extract_table(self, frame: pd.DataFrame) -> str:
        preview = frame.head(200).to_string(index=False)
        stats = frame.describe(include="all").fillna("").to_string()
        return f"Table preview:\n{preview}\n\nTable statistics:\n{stats}"
