import math
import re

from sqlalchemy import select

from app.api.deps import own_provider
from app.core.orchestrator import call_model
from app.db.models import MaterialAsset, MaterialSection
from app.jobs.materials import remote
from app.knowledge.materials import fingerprint, resolve_sources, source_row
from app.knowledge.vectors import rank_vectors
from app.providers.base import CapabilityNotSupported, ProviderError
from app.schemas.materials import Rerank


def keywords(text):
    words = set(re.findall(r"[a-z0-9_]{2,}", text.lower()))
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for word in chinese:
        words.add(word)
        words.update(word[i : i + 2] for i in range(len(word) - 1))
    return words


def cosine(left, right):
    if len(left) != len(right):
        return -1
    return sum(a * b for a, b in zip(left, right, strict=True)) / math.sqrt(
        sum(a * a for a in left) * sum(b * b for b in right)
    )


async def retrieve(request, db, space, query, mode="auto", limit=5):
    rows = db.execute(
        select(MaterialSection, MaterialAsset)
        .join(MaterialAsset, MaterialSection.asset_id == MaterialAsset.id)
        .where(
            MaterialSection.user_id == space.user_id,
            MaterialSection.space_id == space.id,
            MaterialAsset.user_id == space.user_id,
            MaterialAsset.space_id == space.id,
            MaterialAsset.status == "ready",
        )
    ).all()
    config = own_provider(db, space.user_id, space.provider_id, True)
    eligible = [(s, a) for s, a in rows if s.embedding and s.embedding_fingerprint == fingerprint(config)]
    if mode == "embedding" and (not config.capabilities.get("embedding") or not eligible):
        raise CapabilityNotSupported()
    if not rows:
        return {"mode": "keyword_llm_rerank", "results": []}
    if mode != "keyword" and eligible and config.capabilities.get("embedding"):
        vectors = await remote(
            request, db, config, space.id, "material_embedding", lambda adapter: adapter.embed_texts([query])
        )
        scored = [
            (cosine(vectors[0], section.embedding), source_row(section, asset)) for section, asset in eligible
        ]
        if request.app.state.settings.pgvector_enabled:
            indexed = {s.id: source_row(s, a) for s, a in eligible}
            ranks = rank_vectors(db, space.user_id, space.id, fingerprint(config), vectors[0])
            scored = [(score, indexed[sid]) for sid, score in ranks if sid in indexed]
        result_mode = "remote_embedding"
    else:
        terms = keywords(query)
        scored = [
            (
                len(
                    terms
                    & keywords(
                        section.data["heading"]
                        + " "
                        + section.data["summary"]
                        + " "
                        + " ".join(section.data["keywords"])
                    )
                ),
                source_row(section, asset),
            )
            for section, asset in rows
        ]
        result_mode = "keyword_llm_rerank"
        scored = [row for row in scored if row[0] > 0]
    scored.sort(key=lambda row: (-row[0], row[1]["source_id"]))
    candidates = [row for _, row in scored[:20]]
    if not candidates:
        return {"mode": result_mode, "results": []}
    ranked, _ = await call_model(
        request,
        db,
        config,
        space.id,
        "material_rerank",
        Rerank,
        {
            "task": "根据查询仅从候选摘要选择相关证据，按相关性排序。不能凭空创造 source_id；不相关则返回空列表。",
            "query": query,
            "limit": limit,
            "sources": candidates,
        },
    )
    allowed = {s["source_id"] for s in candidates}
    if len(set(ranked.source_ids)) != len(ranked.source_ids) or not set(ranked.source_ids) <= allowed:
        raise ProviderError("invalid_citation", "模型精排引用了候选之外的来源")
    db.expire_all()
    return {"mode": result_mode, "results": resolve_sources(db, space.id, ranked.source_ids[:limit])}


async def teaching_sources(request, db, space, query):
    assets = db.scalars(
        select(MaterialAsset).where(
            MaterialAsset.space_id == space.id, MaterialAsset.status.not_in(["deleted", "deleting"])
        )
    ).all()
    if not assets:
        return []
    result = await retrieve(request, db, space, query)
    if not result["results"] and not space.allow_general_knowledge:
        raise ProviderError(
            "insufficient_material_evidence",
            "教材证据不足，请等待索引完成、补充资料，或在空间设置中允许通用知识补充",
            422,
        )
    return result["results"]
