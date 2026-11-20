"""
Semantic Knowledge Embedding & Vector Search Service (pgvector + deterministic offline fallback).
"""

import hashlib
import math
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import LeadEmbedding
from src.schemas.crm import SemanticSearchResult

EMBEDDING_DIMENSIONS = 768


def compute_deterministic_embedding(text_content: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """
    Produces a normalized 768-dimensional deterministic embedding vector from character n-grams.
    Used when no cloud embedding API is invoked so pgvector HNSW indexing and cosine search
    remain testable and operational in air-gapped environments.
    """
    vec = [0.0] * dimensions
    normalized = (text_content or "").lower().strip()
    if not normalized:
        return vec

    tokens = normalized.split()
    features: list[str] = list(tokens)
    for token in tokens:
        if len(token) >= 3:
            for i in range(len(token) - 2):
                features.append(token[i : i + 3])

    for feat in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def upsert_entity_embedding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    text_content: str,
    chunk_index: int = 0,
) -> LeadEmbedding:
    vector = compute_deterministic_embedding(text_content)
    existing = await session.scalar(
        select(LeadEmbedding).where(
            LeadEmbedding.tenant_id == tenant_id,
            LeadEmbedding.entity_type == entity_type,
            LeadEmbedding.entity_id == entity_id,
            LeadEmbedding.chunk_index == chunk_index,
        )
    )
    if existing:
        existing.text_content = text_content
        existing.embedding = vector
        await session.flush()
        return existing

    record = LeadEmbedding(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        chunk_index=chunk_index,
        text_content=text_content,
        embedding=vector,
    )
    session.add(record)
    await session.flush()
    return record


async def semantic_search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    entity_type: str | None = None,
    limit: int = 5,
) -> tuple[list[SemanticSearchResult], str]:
    query_vec = compute_deterministic_embedding(query)
    bind = session.get_bind()

    if bind is not None and bind.dialect.name == "postgresql":
        vec_literal = "[" + ",".join(str(x) for x in query_vec) + "]"
        sql = """
            SELECT entity_type, entity_id, text_content,
                   1 - (embedding <=> CAST(:qvec AS vector)) AS similarity
            FROM lead_embeddings
            WHERE tenant_id = CAST(:tenant_id AS uuid)
        """
        params: dict = {"qvec": vec_literal, "tenant_id": str(tenant_id), "limit": limit}
        if entity_type:
            sql += " AND entity_type = :entity_type"
            params["entity_type"] = entity_type
        sql += " ORDER BY embedding <=> CAST(:qvec AS vector) LIMIT :limit"

        rows = (await session.execute(text(sql), params)).all()
        results = [
            SemanticSearchResult(
                entity_type=row[0],
                entity_id=row[1],
                text_content=row[2],
                similarity=round(float(row[3]), 4),
            )
            for row in rows
        ]
        return results, "pgvector_hnsw"

    # SQLite fallback for hermetic tests
    stmt = select(LeadEmbedding).where(LeadEmbedding.tenant_id == tenant_id)
    if entity_type:
        stmt = stmt.where(LeadEmbedding.entity_type == entity_type)
    records = list((await session.scalars(stmt)).all())

    scored = [
        SemanticSearchResult(
            entity_type=rec.entity_type,
            entity_id=rec.entity_id,
            text_content=rec.text_content,
            similarity=round(_cosine_similarity(query_vec, list(rec.embedding)), 4),
        )
        for rec in records
    ]
    scored.sort(key=lambda item: item.similarity, reverse=True)
    return scored[:limit], "sqlite_cosine_fallback"
