"""Optional pgvector mirror. Vectors always originate from the user's remote API."""

import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.providers.base import ProviderError


def execute_vector_sql(db, statement, parameters):
    try:
        return db.execute(statement, parameters)
    except SQLAlchemyError:
        raise ProviderError(
            "pgvector_unavailable", "pgvector 扩展或资料向量表不可用，请执行 scripts/pgvector.sql 并重新索引"
        ) from None


def store_vectors(db, sections, enabled):
    if not enabled:
        return
    if db.bind.dialect.name != "postgresql":
        raise ProviderError(
            "pgvector_unavailable", "PGVECTOR_ENABLED 需要 PostgreSQL 和初始化后的 pgvector 表", 422
        )
    for section in sections:
        if section.embedding:
            execute_vector_sql(
                db,
                text(
                    "INSERT INTO material_vectors (section_id, embedding) "
                    "VALUES (:id, CAST(:vector AS vector))"
                ),
                {"id": section.id, "vector": json.dumps(section.embedding)},
            )


def rank_vectors(db, user_id, space_id, fingerprint, vector, limit=20):
    if db.bind.dialect.name != "postgresql":
        raise ProviderError("pgvector_unavailable", "向量检索需要 PostgreSQL pgvector", 422)
    return list(
        execute_vector_sql(
            db,
            text("""
        SELECT s.id, 1 - (v.embedding <=> CAST(:vector AS vector)) AS similarity
        FROM material_vectors v
        JOIN material_sections s ON s.id = v.section_id
        JOIN material_assets a ON a.id = s.asset_id AND a.space_id = s.space_id
        WHERE s.user_id = :user_id AND s.space_id = :space_id
          AND a.user_id = :user_id AND a.status = 'ready'
          AND s.embedding_fingerprint = :fingerprint
          AND vector_dims(v.embedding) = :dimensions
        ORDER BY v.embedding <=> CAST(:vector AS vector), s.id
        LIMIT :limit
    """),
            {
                "vector": json.dumps(vector),
                "user_id": user_id,
                "space_id": space_id,
                "fingerprint": fingerprint,
                "dimensions": len(vector),
                "limit": limit,
            },
        )
    )
