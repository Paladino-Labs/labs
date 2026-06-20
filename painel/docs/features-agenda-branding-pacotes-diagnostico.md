# Diagnóstico — 3 features deferidas (Agenda · Branding · Pacotes multi-item)

**Status:** diagnóstico para implementação (não implementado).
**Data:** 2026-06-19.
**Origem:** sessão pré-push; itens classificados como feature e deferidos. Renames
(Tipos de pacotes/Vendas/Ativas), nome real no header e ajustes de sidebar **já foram
aplicados** nesta sessão — não fazem parte deste documento.

---

## 1. Redesign da Agenda (frontend-only)

**Arquivo:** `painel/app/(dashboard)/agenda/page.tsx` (+ `components/AgendaCalendar.tsx`).

### Estado atual
- Página com cabeçalho contendo: navegação de semana (`‹ Hoje ›`), **toggle Lista/Calendário**, botão **"+ Novo Agendamento"**.
- Vista calendário num container de **altura fixa** (`style={{ height: "calc(100vh - 14rem)" }}`) → o `AgendaCalendar` rola internamente (vertical das horas) **enquanto** a página/`main` também rola → **dois scrolls**. Colunas de profissionais geram **scroll lateral**.
- `viewMode` (list|calendar) com bloco de lista sempre montado (`viewMode === "list" || true`), day-picker de 7 dias e filtros prof/status.

### Alvo (pedido do usuário)
- Maior e **responsivo ao tamanho da tela** (sem altura fixa em `calc`); ocupar a área útil sem criar segundo scroll.
- **Sem scroll lateral.**
- **Remover:** toggle Lista/Calendário, botão "+ Novo Agendamento", seletor de semana/dia.
- Espelhar **exatamente** o visual do protótipo `barberflow-system` (referência visual apenas, não comportamento — ver CLAUDE.md) e das imagens em `OneDrive/Desktop/Paladino/Screenshots`.

### Pré-requisito (passo 0)
Localizar o screenshot específico da Agenda na pasta (não aparece no nível raiz; checar subpastas `Fase *` / `sprint-gap`). O redesign deve casar pixel-a-pixel com ele.

### Pontos de atenção
- Endpoints permanecem os mesmos (`GET /appointments/`, `GET /professionals/`) — **nenhuma mudança de backend**.
- Ações já existentes (detalhe, remarcar, concluir+pagamento, cancelar) devem ser preservadas — só muda o entrypoint (sem o botão "+ Novo" no header; criação via clique em slot já existe: `handleCalendarSlotClick` → `/appointments/new`).
- Remover o seletor de semana/dia muda o modelo de navegação — confirmar com o protótipo qual período a agenda exibe por padrão (dia? semana corrente?) antes de remover `currentDate`/`selectedDay`.
- **Esforço:** médio (reescrita visual de 1 página + ajustes no `AgendaCalendar`).

---

## 2. Expansão / reorganização do Branding (frontend, sem backend)

**Arquivos:** `painel/app/(dashboard)/settings/branding/page.tsx` e `settings/profile/page.tsx`.

### Achado central
Quase tudo que o usuário pediu **já existe** — porém na tela **"Perfil da empresa"** (`settings/profile`), não em "Branding". O endpoint `GET/PATCH /company/profile` (`CompanyProfileOut`) já cobre:

| Campo pedido | Campo existente em `/company/profile` |
|---|---|
| Slogan | `tagline` |
| Breve descrição | `description` |
| Logo | `logo_url` |
| Foto de capa | `cover_url` |
| Galeria de fotos | `gallery_urls[]` |
| Endereço | `address`, `city` |
| WhatsApp | `whatsapp` |
| Link Google Maps | `maps_url` |
| Redes sociais | `instagram_url`, `facebook_url`, `tiktok_url` |
| Avaliações | `google_review_url` |
| Horário de funcionamento | `business_hours` |
| **Link público** | slug + toggle `online_booking_enabled` via `/companies/me` (+ `GET /booking/{slug}/info`) — já implementado em `settings/profile` |

A tela **"Branding"** atual só tem `logo_url`, `primary_color`, `secondary_color`, `font_family`, `favicon_url`, `custom_texts` (de `GET/PUT /tenant/branding`).

### Alvo
Decisão de **IA/organização**, não de backend:
- **Opção A (recomendada):** consolidar a identidade visual numa só superfície — mover/duplicar os campos de `/company/profile` para dentro de "Branding" (ou renomear "Branding" para "Identidade da empresa" e absorver "Perfil da empresa"). Evita o usuário procurar em duas telas.
- **Opção B:** manter as duas telas e apenas **cross-linkar** (um aviso em Branding apontando para "Perfil da empresa" para capa/slogan/galeria/contato).
- Expor edição do **nome da empresa** (hoje editável só via `PATCH /companies/me`, sem campo na UI) — adicionar input de `name`.

### Pontos de atenção
- **Backend:** nenhum campo novo necessário (apenas, se quiser, surfacing do `name`). Confirmar shape de `CompanyProfileOut` no backend antes (campos podem ser nullable).
- Uploads de imagem já usam `POST /uploads/` (visto em `settings/profile`).
- **Esforço:** médio (reorg de formulário; sem backend).

---

## 3. Pacotes e assinaturas com múltiplos serviços + produtos (backend + frontend)

**Esta é a única das três que exige backend — escopo Estágio 1+.**

### Estado atual (limitação de modelo)
- `Package.service_id` e `Plan.service_id` são **FK únicas e nullable** para `services` (`infrastructure/db/models/package.py`, `subscription.py`). Um pacote/plano cobre **um único serviço** (ou genérico quando NULL). **Não há** produtos, múltiplos itens nem quantidades por item.
- Crédito/cota gerado na compra (`CustomerCredit`) também não tem FK de serviço (limitação já documentada — ver memória [[backend-dividas-5a5b]]).

### Alvo
Permitir compor pacote/assinatura a partir de **N itens** (serviços e/ou produtos) com quantidade — ex.: "2 cortes + 5 barbas", "4 cortes + 2 hidratações", serviços e produtos mesclados.

### Trabalho de backend (significativo)
1. Modelo novo de junção: `package_items` / `plan_items` (`{package_id|plan_id, item_type: SERVICE|PRODUCT, service_id?, product_id?, quantity}`) com migration.
2. Schemas/endpoints de Package e Plan passam a aceitar/retornar `items[]` (hoje `service_id` único).
3. Lógica de compra (`packages.purchase`, assinatura) e de **concessão de cota** precisa gerar crédito **por item** — repensar `CustomerCredit` (FK por serviço/produto ou tabela de itens de crédito).
4. Consumo de cota (resolução de qual crédito abater no agendamento/venda) precisa casar item↔serviço/produto.
5. Migração de dados dos pacotes/planos existentes (`service_id` → 1 item).

### Trabalho de frontend
- Formulários de criar/editar pacote e plano (`pacotes/page.tsx`, `assinaturas/planos/page.tsx`): trocar o select único de serviço por um **editor de itens** (lista add/remove com serviço OU produto + quantidade).
- Telas de cota/consumo (cliente/portal) refletem múltiplos itens.

### Pontos de atenção
- Quebra de contrato de API (de `service_id` para `items[]`) → versionar ou aceitar ambos na transição.
- **Esforço:** grande (migration + service de compra/cota + 2 formulários + telas de cota). Recomendado tratar como sprint dedicado de Estágio 1+, alinhado ao GAP de eixos CUSTOM já registrado.
