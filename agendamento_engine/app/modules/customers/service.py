import re
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Customer
from app.infrastructure.db.models.appointment import Appointment
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate, CustomerAppointmentItem


def normalize_phone(phone: str) -> str:
    """
    Normaliza número de telefone brasileiro para E.164 sem o '+'.

    Regras aplicadas em ordem:
      1. Remove tudo que não é dígito.
      2. Garante prefixo DDI 55.
      3. Se o número tem 13 dígitos (55 + DDD + 9 + 8) → celular completo, mantém.
      4. Se tem 12 dígitos (55 + DDD + 8):
           - 8 dígitos locais começam com 2, 3 ou 4 → fixo/comercial, mantém sem 9.
           - Caso contrário → celular sem o 9, insere o 9 após o DDD.

    Exemplos:
      "62 9 8888-7777"  → "5562988887777"  (celular com 9, já completo)
      "62 8888-7777"    → "5562988887777"  (celular sem 9, insere)
      "62 3333-7777"    → "55623333777"   (fixo/comercial, não insere 9)
      "+55 62 98888-7777" → "5562988887777"
    """
    digits = re.sub(r"\D", "", phone)

    # Garante DDI 55
    if digits.startswith("55"):
        pass
    elif len(digits) <= 11:
        digits = "55" + digits

    # A partir daqui digits começa com "55"
    # Estrutura esperada: 55 (2) + DDD (2) + local (8 ou 9)
    suffix = digits[4:]  # tudo após "55" + DDD

    if len(digits) == 13:
        # 55 + DDD(2) + 9 + 8 dígitos → celular completo, ok
        return digits

    if len(digits) == 12:
        # 55 + DDD(2) + 8 dígitos locais
        first_local = suffix[0] if suffix else ""
        if first_local in ("2", "3", "4"):
            # Fixo ou comercial — não adiciona 9
            return digits
        else:
            # Celular sem o 9 — insere após o DDD (posição 4)
            return digits[:4] + "9" + digits[4:]

    # Formato inesperado — retorna como está (melhor do que rejeitar)
    return digits


def _find_by_phone_smart(db: Session, company_id: UUID, phone: str) -> Optional[Customer]:
    """
    Busca cliente com lógica inteligente de deduplicação para números brasileiros.

    Fluxo:
      1. Normaliza o número de entrada.
      2. Tenta match exato no banco.
      3. Se não achar E o número tem 12 dígitos (pode ser celular sem 9):
           - Extrai os 8 últimos dígitos e o DDD.
           - Busca todos os clientes da empresa cujo phone termina com esses 8 dígitos.
           - Filtra pelo mesmo DDD — se achar, é o mesmo cliente.
      4. Se não achar E o número tem 13 dígitos (celular com 9):
           - Tenta buscar a versão sem o 9 (12 dígitos) no banco — cliente cadastrado
             antes da portabilidade ou via canal antigo.

    Retorna o Customer encontrado ou None.
    """
    normalized = normalize_phone(phone)

    # 1. Match exato
    customer = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.phone == normalized,
        Customer.active == True,
    ).first()
    if customer:
        return customer

    ddd        = normalized[2:4]   # posição fixa após "55"
    last8      = normalized[-8:]   # últimos 8 dígitos (número local sem o 9)

    if len(normalized) == 12:
        # Entrada era celular sem 9 → procura versão com 9 no banco
        with_nine = normalized[:4] + "9" + normalized[4:]
        customer = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.phone == with_nine,
            Customer.active == True,
        ).first()
        if customer:
            return customer

    if len(normalized) == 13:
        # Entrada era celular com 9 → procura versão sem 9 no banco
        without_nine = normalized[:4] + normalized[5:]   # remove o 9 da posição 4
        customer = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.phone == without_nine,
            Customer.active == True,
        ).first()
        if customer:
            return customer

    # Fallback: busca pelos 8 últimos dígitos + DDD para pegar variações não previstas
    candidates = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.phone.like(f"%{last8}"),
        Customer.active == True,
    ).all()
    for c in candidates:
        if c.phone[2:4] == ddd:
            return c

    return None


def list_customers(db: Session, company_id: UUID):
    return (
        db.query(Customer)
        .filter(Customer.company_id == company_id, Customer.active == True)
        .order_by(Customer.name)
        .all()
    )


def get_customer_or_404(db: Session, company_id: UUID, customer_id: UUID) -> Customer:
    c = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == company_id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return c


def create_customer(db: Session, company_id: UUID, data: CustomerCreate) -> Customer:
    """
    Cria cliente normalizando o telefone.
    Usa _find_by_phone_smart para evitar duplicatas mesmo com variações do 9.
    """
    normalized = normalize_phone(data.phone)

    existing = _find_by_phone_smart(db, company_id, data.phone)
    if existing:
        raise HTTPException(status_code=409, detail="Telefone já cadastrado para outro cliente")

    payload = data.model_dump()
    payload["phone"] = normalized
    customer = Customer(company_id=company_id, **payload)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def get_by_phone(db: Session, company_id: UUID, phone: str) -> Optional[Customer]:
    """
    Busca cliente pelo telefone com deduplicação inteligente do dígito 9.
    Usado pelo bot para identificar clientes via WhatsApp.
    """
    return _find_by_phone_smart(db, company_id, phone)


def get_or_create_by_phone(
    db: Session, company_id: UUID, phone: str, name: str
) -> Customer:
    """
    Retorna o cliente existente ou cria um novo.
    A busca usa deduplicação inteligente — variações do mesmo número
    retornam o cadastro existente em vez de criar duplicata.
    """
    customer = _find_by_phone_smart(db, company_id, phone)
    if customer:
        return customer

    # Não encontrou nenhuma variação — criar novo cadastro com número normalizado
    normalized = normalize_phone(phone)
    customer = Customer(company_id=company_id, name=name, phone=normalized)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(db: Session, company_id: UUID, customer_id: UUID, data: CustomerUpdate) -> Customer:
    customer = get_customer_or_404(db, company_id, customer_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


def list_appointments_for_customer(
    db: Session, company_id: UUID, customer_id: UUID
) -> list[CustomerAppointmentItem]:
    """Histórico completo de agendamentos do cliente, ordenado do mais recente."""
    get_customer_or_404(db, company_id, customer_id)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == customer_id,
        )
        .order_by(Appointment.start_at.desc())
        .all()
    )

    result = []
    for a in appointments:
        result.append(CustomerAppointmentItem(
            id=a.id,
            start_at=a.start_at.isoformat(),
            end_at=a.end_at.isoformat(),
            status=a.status,
            service_names=[s.service_name for s in a.services],
            professional_name=a.professional.name if a.professional else None,
            total_amount=str(a.total_amount),
        ))
    return result