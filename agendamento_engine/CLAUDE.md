-**Sprint atual:** Sprint 1 em andamento (Fase 1 — Fundação técnica)
+**Sprint atual:** Sprint 2 em andamento (Fase 1 — Fundação técnica)

 ## Stack e infraestrutura
 
+- slowapi ativo — rate limit 10 req/min/IP em POST /auth/login (X-Forwarded-For)
+- Uploads: Supabase Storage (dual-write ativo; script de migração de URLs pendente de execução)
+- EXCLUDE CONSTRAINT ativa em appointments (btree_gist + tsrange, company_id + professional_id)
 - FastAPI 0.115 · SQLAlchemy 2.0 · Alembic

 ## Convenções críticas

+- EXCLUDE CONSTRAINT no_overlap_per_professional: filtro WHERE status NOT IN
+  ('CANCELLED','FAILED','EXPIRED') — NO_SHOW e COMPLETED ativam a constraint
+- Upload: endpoint retorna URL Supabase; gravação local foi removida

 ## O que NÃO fazer

+- Não reintroduzir os.makedirs("static/uploads") — removido de main.py
+- Não usar URLs de volume local (/static/uploads/) — fonte de verdade é Supabase Storage