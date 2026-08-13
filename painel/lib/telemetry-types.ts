/**
 * Tipos da telemetria do bot — S-painel-telemetria.
 *
 * Shapes reais de `GET/PUT /platform/telemetry/*` (conferidos em
 * `app/modules/platform/telemetry_service.py`). Os endpoints devolvem dict
 * livre, não schema Pydantic tipado — mesma situação do portal, mesmo
 * tratamento: o contrato fica aqui, num lugar só.
 */

/** Uma linha da lista: um interlocutor, agrupado por whatsapp_hash. */
export interface TelemetryConversationRow {
  whatsapp_hash: string
  whatsapp_masked: string | null
  company_id: string | null
  company_name: string | null
  message_count: number
  /** O indicador que faz o Silva escolher qual conversa ler. */
  not_understood_count: number
  first_at: string | null
  last_at: string | null
}

export interface TelemetryConversationList {
  total: number
  items: TelemetryConversationRow[]
}

/** O essencial, que fica INLINE em cada mensagem do cliente. */
export interface TelemetryDiagnosis {
  not_understood: boolean
  /** MENU_FALLBACK | SHADOW_NOT_ROUTED | UNREADABLE_TYPE | null */
  reason: string | null
  classified: boolean
  intent: string | null
  confidence: number | null
  routing_decision: string | null
  /** O sintoma que interessa: o bot devolveu menu genérico. */
  generic_menu: boolean
}

/** O diagnóstico completo, atrás do expansível. */
export interface TelemetryDetail {
  fsm_state: string | null
  fsm_state_after: string | null
  message_type: string | null
  outcome: string | null
  duration_ms: number | null
  event: string | null
  regex: Record<string, unknown> | null
  llm: Record<string, unknown> | null
  final: Record<string, unknown> | null
  routing: Record<string, unknown> | null
  handler: string | null
  dispatch_path: string[] | null
  dispatch_detail: Record<string, unknown> | null
}

export interface TelemetryOutbound {
  kind: string
  text: string
  ok: boolean
}

/** O rótulo humano. `null` = não marcada (o que está certo fica em branco). */
export interface TelemetryLabel {
  understood: string | null
  expected_intent: string | null
  note: string | null
  updated_at?: string | null
}

export interface TelemetryMessage {
  trace_id: string
  received_at: string | null
  text: string | null
  diagnosis: TelemetryDiagnosis
  detail: TelemetryDetail
  outbound: TelemetryOutbound[]
  label: TelemetryLabel | null
}

export interface TelemetryConversation {
  whatsapp_hash: string
  whatsapp_masked: string | null
  company_id: string | null
  message_count: number
  not_understood_count: number
  messages: TelemetryMessage[]
}

export interface TelemetryCatalog {
  expected_intents: string[]
  understood: string[]
}

export interface TelemetryLabelResponse {
  trace_id: string
  label: TelemetryLabel | null
}

/**
 * Rótulos legíveis do catálogo. O backend é a FONTE da lista
 * (`GET /platform/telemetry/catalog`) — este mapa só traduz para exibição.
 * Chave desconhecida cai no próprio valor, então um rótulo novo criado no
 * backend aparece na tela sem precisar de deploy do frontend.
 */
export const EXPECTED_INTENT_LABELS: Record<string, string> = {
  agendar: "Agendar",
  cancelar: "Cancelar",
  remarcar: "Remarcar",
  consultar: "Consultar",
  saudacao: "Saudação",
  agradecimento: "Agradecimento",
  preco: "Preço",
  disponibilidade: "Disponibilidade",
  produto: "Produto",
  pacote: "Pacote",
  humano: "Humano",
  outro: "Outro",
}

export const UNDERSTOOD_LABELS: Record<string, string> = {
  YES: "Entendeu",
  NO: "Não entendeu",
  WRONG: "Entendeu errado",
}

/** Por que a mensagem conta como não entendida — dito em português. */
export const NOT_UNDERSTOOD_REASON_LABELS: Record<string, string> = {
  MENU_FALLBACK: "Menu genérico",
  SHADOW_NOT_ROUTED: "Menu genérico (shadow)",
  UNREADABLE_TYPE: "Tipo não lido",
}
