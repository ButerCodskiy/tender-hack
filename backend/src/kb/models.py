"""Декларативные модели базы данных подсистемы базы знаний (kb)."""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base


class KbDocumentModel(Base):
    """Модель документа нормативного регламента или методички."""

    __tablename__ = "kb_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'indexing', 'indexed', 'failed', 'deprecated')",
            name="chk_document_status",
        ),
        Index("idx_kb_documents_status", "status"),
    )

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    regime: Mapped[str | None] = mapped_column(
        String(32), default="MOS_PORTAL", nullable=True
    )
    edition_date: Mapped[date | None] = mapped_column(
        Date, server_default=func.current_date(), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="uploaded", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    nodes: Mapped[list["KbNodeModel"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<KbDocumentModel doc_id={self.doc_id} status={self.status}>"


class KbNodeModel(Base):
    """Модель структурного узла абстрактного синтаксического дерева документа."""

    __tablename__ = "kb_nodes"
    __table_args__ = (
        Index("idx_kb_nodes_lookup", "doc_id", "article_no", "part_no"),
        Index("idx_kb_nodes_path", "doc_id", "section_path"),
        Index("idx_kb_nodes_parent", "parent_node_id"),
    )

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("kb_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_node_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("kb_nodes.node_id", ondelete="CASCADE"),
        nullable=True,
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    article_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    part_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    full_content: Mapped[str] = mapped_column(Text, nullable=False)
    table_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    document: Mapped["KbDocumentModel"] = relationship(back_populates="nodes")
    parent_node: Mapped["KbNodeModel | None"] = relationship(
        remote_side=[node_id],
        back_populates="children_nodes",
    )
    children_nodes: Mapped[list["KbNodeModel"]] = relationship(
        back_populates="parent_node",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chunks: Mapped[list["KbChunkModel"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<KbNodeModel node_id={self.node_id} level={self.level}>"


class KbChunkModel(Base):
    """Модель атомарного фрагмента документа для векторного и гибридного поиска."""

    __tablename__ = "kb_chunks"
    __table_args__ = (Index("idx_kb_chunks_node", "node_id"),)

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("kb_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    hyp_questions: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    embedding_model_version: Mapped[str] = mapped_column(
        String(32), default="bge-m3", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    node: Mapped["KbNodeModel"] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<KbChunkModel chunk_id={self.chunk_id} node_id={self.node_id}>"
        )


class KbArticleReferenceModel(Base):
    """Модель нормативного графа перекрестных ссылок между статьями."""

    __tablename__ = "kb_article_references"
    __table_args__ = (
        Index("idx_kb_refs_from", "from_node_id"),
        Index("idx_kb_refs_to", "to_node_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    from_node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("kb_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    to_node_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("kb_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_label: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<KbArticleReferenceModel from={self.from_node_id} to={self.to_node_id}>"


class FaqModerationQueueModel(Base):
    """Модель очереди черновиков FAQ для контура самообучения базы знаний."""

    __tablename__ = "faq_moderation_queue"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('normative', 'procedural')",
            name="chk_faq_kind",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="chk_faq_status",
        ),
        Index(
            "idx_faq_moderation_status",
            "status",
            postgresql_where="status = 'PENDING'",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="procedural"
    )
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    linked_regulation_chunk_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("kb_chunks.chunk_id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING"
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<FaqModerationQueueModel id={self.id} status={self.status}>"
