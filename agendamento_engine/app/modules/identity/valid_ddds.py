"""
Lista de DDDs (códigos de área) válidos no Brasil.
Fonte: ANATEL — planos de numeração vigentes.

Usado exclusivamente pela validação de telefone de formulários
públicos (validate_user_phone_input). NÃO usado por normalize_phone_e164
nem pelo bot.
"""
VALID_DDDS: frozenset[str] = frozenset({
    # Região 1 — SP
    "11", "12", "13", "14", "15", "16", "17", "18", "19",
    # Região 2 — RJ, ES
    "21", "22", "24", "27", "28",
    # Região 3 — MG
    "31", "32", "33", "34", "35", "37", "38",
    # Região 4 — PR, SC
    "41", "42", "43", "44", "45", "46", "47", "48", "49",
    # Região 5 — RS
    "51", "53", "54", "55",
    # Região 6 — DF, GO, TO, MT, MS, AC, RO
    "61", "62", "63", "64", "65", "66", "67", "68", "69",
    # Região 7 — BA, SE, PE, AL, PB, RN, CE, PI, MA
    "71", "73", "74", "75", "77", "79",
    "81", "82", "83", "84", "85", "86", "87", "88", "89",
    # Região 9 — PA, AM, RR, AP
    "91", "92", "93", "94", "95", "96", "97", "98", "99",
})
