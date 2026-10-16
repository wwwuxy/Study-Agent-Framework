-- 在已执行 Alembic 0002 的 PostgreSQL 数据库中运行。
-- 需要数据库管理员预先安装 pgvector 扩展包，并有 CREATE EXTENSION 权限。
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS material_vectors (
    section_id VARCHAR(36) PRIMARY KEY REFERENCES material_sections(id) ON DELETE CASCADE,
    embedding vector NOT NULL
);
-- 不固定维度，以允许用户模型不同；先按租户/模型指纹过滤，再精确余弦检索。
-- 本表仅保存远端 API 产生的向量，不执行任何本地 Embedding。
