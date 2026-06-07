from src.documents.pipeline import DocumentPipeline, RetrievedChunk
from src.storage.database import Database
from src.agents.prompts import DOCUMENT_AGENT_PROMPT


class DocumentAgent:
    name = "Document Agent"
    instructions = DOCUMENT_AGENT_PROMPT

    def __init__(self, db: Database, documents: DocumentPipeline):
        self.db = db
        self.documents = documents

    def retrieve_evidence(self, session_id: str, run_id: str, query: str) -> list[RetrievedChunk]:
        chunks = self.documents.retrieve(session_id, query)
        self.db.add_tool_call(
            run_id,
            session_id,
            "search_uploaded_documents",
            {"query": query, "top_k": self.documents.config.retrieval_top_k},
            f"Retrieved {len(chunks)} relevant document chunks.",
        )
        self.db.add_step(
            run_id,
            session_id,
            self.name,
            f"Retrieved document evidence from {len(chunks)} chunks using Document Agent instructions.",
        )
        return chunks

    def summarize_evidence(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "No relevant uploaded document evidence was found."
        bullets = []
        for chunk in chunks[:5]:
            snippet = chunk.content[:420].strip()
            bullets.append(f"- Document chunk {chunk.metadata['chunk_index']} score {chunk.score:.2f}: {snippet}")
        return "\n".join(bullets)
