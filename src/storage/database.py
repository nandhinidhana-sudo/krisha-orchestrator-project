import sqlite3
from pathlib import Path
from typing import Any

from src.utils import estimate_tokens, from_json, new_id, to_json, utc_now


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                create table if not exists sessions (
                    id text primary key,
                    title text not null,
                    status text not null default 'active',
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists messages (
                    id text primary key,
                    session_id text not null,
                    role text not null,
                    content text not null,
                    token_estimate integer not null,
                    summarized integer not null default 0,
                    created_at text not null
                );

                create table if not exists conversation_summaries (
                    id text primary key,
                    session_id text not null,
                    summary text not null,
                    covered_message_count integer not null,
                    created_at text not null
                );

                create table if not exists documents (
                    id text primary key,
                    session_id text not null,
                    filename text not null,
                    file_type text not null,
                    file_path text not null,
                    extracted_path text,
                    status text not null,
                    chunk_count integer not null default 0,
                    created_at text not null
                );

                create table if not exists document_chunks (
                    id text primary key,
                    document_id text not null,
                    session_id text not null,
                    chunk_index integer not null,
                    content text not null,
                    token_estimate integer not null,
                    metadata_json text not null,
                    created_at text not null
                );

                create table if not exists agent_runs (
                    id text primary key,
                    session_id text not null,
                    user_request text not null,
                    final_response text,
                    status text not null,
                    duration_ms integer not null default 0,
                    created_at text not null,
                    completed_at text
                );

                create table if not exists agent_steps (
                    id text primary key,
                    run_id text not null,
                    session_id text not null,
                    agent_name text not null,
                    summary text not null,
                    created_at text not null
                );

                create table if not exists tool_calls (
                    id text primary key,
                    run_id text not null,
                    session_id text not null,
                    tool_name text not null,
                    arguments_json text not null,
                    result_summary text not null,
                    status text not null,
                    latency_ms integer not null default 0,
                    created_at text not null
                );

                create table if not exists artifacts (
                    id text primary key,
                    session_id text not null,
                    run_id text,
                    kind text not null,
                    title text not null,
                    content_json text not null,
                    created_at text not null
                );

                create table if not exists citations (
                    id text primary key,
                    session_id text not null,
                    run_id text,
                    source_type text not null,
                    source_ref text not null,
                    snippet text not null,
                    created_at text not null
                );

                create table if not exists user_preferences (
                    id text primary key,
                    session_id text not null,
                    key text not null,
                    value text not null,
                    updated_at text not null
                );

                create table if not exists errors (
                    id text primary key,
                    session_id text,
                    run_id text,
                    error_type text not null,
                    message text not null,
                    created_at text not null
                );
                """
            )

    def create_session(self, title: str) -> str:
        session_id = new_id()
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "insert into sessions (id, title, created_at, updated_at) values (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return session_id

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("select * from sessions order by updated_at desc").fetchall()
        return [dict(row) for row in rows]

    def touch_session(self, session_id: str) -> None:
        with self.connect() as db:
            db.execute("update sessions set updated_at = ? where id = ?", (utc_now(), session_id))

    def add_message(self, session_id: str, role: str, content: str) -> str:
        message_id = new_id()
        with self.connect() as db:
            db.execute(
                """
                insert into messages (id, session_id, role, content, token_estimate, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, estimate_tokens(content), utc_now()),
            )
        self.touch_session(session_id)
        return message_id

    def list_messages(self, session_id: str, include_summarized: bool = True) -> list[dict[str, Any]]:
        query = "select * from messages where session_id = ?"
        params: tuple[Any, ...] = (session_id,)
        if not include_summarized:
            query += " and summarized = 0"
        query += " order by created_at asc"
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def latest_summary(self, session_id: str) -> str:
        with self.connect() as db:
            row = db.execute(
                "select summary from conversation_summaries where session_id = ? order by created_at desc limit 1",
                (session_id,),
            ).fetchone()
        return row["summary"] if row else ""

    def add_summary(self, session_id: str, summary: str, covered_message_ids: list[str]) -> str:
        summary_id = new_id()
        with self.connect() as db:
            db.execute(
                """
                insert into conversation_summaries
                (id, session_id, summary, covered_message_count, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (summary_id, session_id, summary, len(covered_message_ids), utc_now()),
            )
            db.executemany(
                "update messages set summarized = 1 where id = ?",
                [(message_id,) for message_id in covered_message_ids],
            )
        return summary_id

    def add_document(self, session_id: str, filename: str, file_type: str, file_path: Path) -> str:
        document_id = new_id()
        with self.connect() as db:
            db.execute(
                """
                insert into documents
                (id, session_id, filename, file_type, file_path, status, created_at)
                values (?, ?, ?, ?, ?, 'uploaded', ?)
                """,
                (document_id, session_id, filename, file_type, str(file_path), utc_now()),
            )
        return document_id

    def update_document_processed(self, document_id: str, extracted_path: Path, chunk_count: int) -> None:
        with self.connect() as db:
            db.execute(
                """
                update documents
                set extracted_path = ?, chunk_count = ?, status = 'indexed'
                where id = ?
                """,
                (str(extracted_path), chunk_count, document_id),
            )

    def add_document_chunk(
        self,
        document_id: str,
        session_id: str,
        chunk_index: int,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        chunk_id = new_id()
        with self.connect() as db:
            db.execute(
                """
                insert into document_chunks
                (id, document_id, session_id, chunk_index, content, token_estimate, metadata_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    session_id,
                    chunk_index,
                    content,
                    estimate_tokens(content),
                    to_json(metadata),
                    utc_now(),
                ),
            )
        return chunk_id

    def list_document_chunks(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "select * from document_chunks where session_id = ? order by created_at asc, chunk_index asc",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_documents(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "select id, filename, file_type, status, chunk_count, created_at from documents where session_id = ? order by created_at desc",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def start_run(self, session_id: str, user_request: str) -> str:
        run_id = new_id()
        with self.connect() as db:
            db.execute(
                """
                insert into agent_runs (id, session_id, user_request, status, created_at)
                values (?, ?, ?, 'running', ?)
                """,
                (run_id, session_id, user_request, utc_now()),
            )
        return run_id

    def complete_run(self, run_id: str, final_response: str, duration_ms: int, status: str = "completed") -> None:
        with self.connect() as db:
            db.execute(
                """
                update agent_runs
                set final_response = ?, duration_ms = ?, status = ?, completed_at = ?
                where id = ?
                """,
                (final_response, duration_ms, status, utc_now(), run_id),
            )

    def add_step(self, run_id: str, session_id: str, agent_name: str, summary: str) -> None:
        with self.connect() as db:
            db.execute(
                """
                insert into agent_steps (id, run_id, session_id, agent_name, summary, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (new_id(), run_id, session_id, agent_name, summary, utc_now()),
            )

    def add_tool_call(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result_summary: str,
        status: str = "success",
        latency_ms: int = 0,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                insert into tool_calls
                (id, run_id, session_id, tool_name, arguments_json, result_summary, status, latency_ms, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    run_id,
                    session_id,
                    tool_name,
                    to_json(arguments),
                    result_summary,
                    status,
                    latency_ms,
                    utc_now(),
                ),
            )

    def add_artifact(self, session_id: str, run_id: str | None, kind: str, title: str, content: Any) -> str:
        artifact_id = new_id()
        with self.connect() as db:
            db.execute(
                """
                insert into artifacts (id, session_id, run_id, kind, title, content_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, session_id, run_id, kind, title, to_json(content), utc_now()),
            )
        return artifact_id

    def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "select * from artifacts where session_id = ? order by created_at desc",
                (session_id,),
            ).fetchall()
        artifacts = []
        for row in rows:
            item = dict(row)
            item["content"] = from_json(item.pop("content_json"))
            artifacts.append(item)
        return artifacts

    def list_agent_runs(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                select id, status, duration_ms, substr(user_request, 1, 120) as user_request,
                       created_at, completed_at
                from agent_runs
                where session_id = ?
                order by created_at desc
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_tool_calls(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                select tool_name, status, latency_ms, result_summary, created_at
                from tool_calls
                where session_id = ?
                order by created_at desc
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def token_summary(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            message_tokens = db.execute(
                "select coalesce(sum(token_estimate), 0) as total from messages where session_id = ?",
                (session_id,),
            ).fetchone()["total"]
            chunk_tokens = db.execute(
                "select coalesce(sum(token_estimate), 0) as total from document_chunks where session_id = ?",
                (session_id,),
            ).fetchone()["total"]
        return [
            {"source": "messages", "tokens": message_tokens},
            {"source": "document_chunks", "tokens": chunk_tokens},
        ]
