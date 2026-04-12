# GUIA DE MIGRAÇÃO — substituindo o backend antigo pelo novo

## Estrutura de pastas que vai substituir

Dentro de `agendamento_engine/`, a pasta `app/` inteira será substituída.
O restante (alembic, .env, venv) permanece intocado.

## Passo a passo

### 1. Faça backup do projeto atual
```bash
cd C:\dev\paladino
xcopy agendamento_engine agendamento_engine_backup /E /I
```

### 2. Substitua a pasta app/
```bash
# Remove o app antigo
rmdir /S /Q agendamento_engine\app

# Copia o app novo (gerado pelo Claude)
xcopy paladino_novo\app agendamento_engine\app /E /I
```

### 3. Atualize o requirements.txt
```bash
copy /Y paladino_novo\requirements.txt agendamento_engine\requirements.txt
```

### 4. Instale as dependências novas
```bash
cd agendamento_engine
venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Verifique o .env
O arquivo `.env` já existe com sua DATABASE_URL do Supabase.
Adicione a variável SECRET_KEY se ainda não tiver:
```
SECRET_KEY=sua-chave-aqui
```

### 6. Teste a inicialização
```bash
uvicorn app.main:app --reload
```

Acesse: http://localhost:8000/docs

### 7. Compatibilidade com o banco existente

O banco no Supabase não muda — os modelos novos mapeiam
para as mesmas tabelas. Pontos de atenção:

| Código antigo       | Código novo          | Tabela no banco |
|---------------------|----------------------|-----------------|
| `Client`            | `Customer`           | `clients`       |
| `blocked_slots`     | `ScheduleBlock`      | `schedule_blocks` ⚠️ |
| `app/db/models.py`  | `infrastructure/db/models/` | — |

⚠️ `schedule_blocks` é uma tabela NOVA. Se o seu banco ainda
usa `blocked_slots`, rode esta migration no Supabase antes:

```sql
-- Cria a tabela nova (se ainda não existir)
CREATE TABLE IF NOT EXISTS schedule_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id),
    professional_id UUID NOT NULL REFERENCES professionals(id),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 8. Rotas que mudaram

| Antes               | Agora                |
|---------------------|----------------------|
| `POST /login`       | `POST /auth/login`   |
| `GET /me`           | `GET /auth/me`       |
| `GET /clients`      | `GET /customers`     |
| `POST /clients`     | `POST /customers`    |

Atualize o frontend para usar as novas rotas após a migração.

## O que ainda falta (próximos passos)
- Painel administrativo (telas de login, clientes, profissionais, serviços)
- Link de agendamento público
- WhatsApp bot
