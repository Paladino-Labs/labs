from decimal import Decimal
from typing import List

from app.infrastructure.db.models import AppointmentService, Service


def build_snapshots(services: List[Service]) -> tuple[List[AppointmentService], Decimal, int]:
    """
    Cria snapshots imutáveis dos serviços no momento do agendamento.
    Retorna (snapshots, subtotal, duration_total_minutes).
    """
    snapshots = []
    subtotal = Decimal("0")
    total_minutes = 0

    for s in services:
        snapshots.append(AppointmentService(
            service_id=s.id,
            service_name=s.name,
            duration_snapshot=Decimal(str(s.duration)),
            price_snapshot=s.price,
        ))
        subtotal += s.price
        total_minutes += s.duration

    return snapshots, subtotal, total_minutes
