from sqlalchemy.orm import Session, joinedload
from sqlalchemy import exc
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException

from app.domain.services.availability_engine import generate_available_slots
from app.domain.services.financial import calculate_commission

from app.db.models import (
    Appointment,
    AppointmentService as AppointmentServiceModel,
    AppointmentStatusLog,
    Service,
    Professional,
    ProfessionalService,
    CompanySettings,
    Client
)
from app.api.schemas import appointment_schema


ALLOWED_TRANSITIONS = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["completed", "no_show", "cancelled"],
    "completed": [],
    "cancelled": [],
    "no_show": []
}


# =========================
# CREATE APPOINTMENT
# =========================
def create_appointment(db: Session, data: appointment_schema.AppointmentCreate, current_user):

    company_id = current_user.company_id

    start_at = data.start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    if start_at < now + timedelta(minutes=30):
        raise HTTPException(400, "Agendamento deve ter pelo menos 30 minutos de antecedência")

    try:
        # 🔹 Profissional
        professional = db.query(Professional).filter(
            Professional.id == data.professional_id,
            Professional.company_id == company_id,
            Professional.active == True
        ).first()

        if not professional:
            raise HTTPException(404, "Profissional não encontrado")

        # 🔹 Cliente
        client = db.query(Client).filter(
            Client.id == data.client_id,
            Client.company_id == company_id
        ).first()

        if not client:
            raise HTTPException(404, "Cliente não encontrado")

        # 🔹 Config
        settings = db.query(CompanySettings).filter(
            CompanySettings.company_id == company_id
        ).first()

        default_commission = (
            Decimal(settings.default_commission_percentage)
            if settings else Decimal("40.0")
        )

        subtotal = Decimal("0.00")
        commission_total = Decimal("0.00")
        services = []

        # 🔹 Serviços
        for s in data.services:
            service = db.query(Service).filter(
                Service.id == s.service_id,
                Service.company_id == company_id,
                Service.active == True
            ).first()

            if not service:
                raise HTTPException(400, f"Serviço inválido: {s.service_id}")

            link = db.query(ProfessionalService).join(Professional).filter(
                ProfessionalService.professional_id == data.professional_id,
                ProfessionalService.service_id == s.service_id,
                Professional.company_id == company_id
            ).first()

            if not link:
                raise HTTPException(
                    400,
                    f"Profissional não executa o serviço: {service.name}"
                )

            price = Decimal(service.price)

            services.append(service)
            subtotal += price

            percentage = (
                Decimal(link.commission_percentage)
                if link.commission_percentage is not None
                else default_commission
            )

            commission_total += calculate_commission(price, percentage)

        # 💰 Totais
        discount = Decimal("0.00")
        total = subtotal - discount

        # ⏱️ Duração
        total_duration = sum([s.duration or 0 for s in services])
        end_at = start_at + timedelta(minutes=total_duration)

        # 🔥 Validação disponibilidade
        available_slots = generate_available_slots(
            db=db,
            professional_id=data.professional_id,
            company_id=company_id,
            target_date=start_at.date(),
            duration_minutes=total_duration
        )

        available_slots_dt = available_slots
        
        if start_at.replace(second=0, microsecond=0) not in [
            dt.replace(second=0, microsecond=0) for dt in available_slots_dt
        ]:
            raise HTTPException(400, "Horário inválido ou indisponível")

        # 🔑 Idempotência
        idempotency_key = data.idempotency_key or str(uuid4())

        # 🧱 Criar
        appointment = Appointment(
            company_id=company_id,
            professional_id=data.professional_id,
            client_id=data.client_id,
            start_at=start_at,
            end_at=end_at,
            subtotal_amount=subtotal,
            discount_amount=discount,
            total_amount=total,
            total_commission=commission_total,
            idempotency_key=idempotency_key,
            status="pending",
            financial_status="pending",
            version=1
        )

        db.add(appointment)
        db.flush()

        # 🧾 Snapshot
        for service in services:
            db.add(AppointmentServiceModel(
                appointment_id=appointment.id,
                service_id=service.id,
                service_name=service.name,
                duration_snapshot=service.duration,
                price_snapshot=Decimal(service.price)
            ))

        # 📜 Log
        db.add(AppointmentStatusLog(
            appointment_id=appointment.id,
            from_status=None,
            to_status="pending"
        ))

        db.commit()
        db.refresh(appointment)

        return appointment

    except exc.IntegrityError as e:
        db.rollback()
        error_str = str(e.orig)

        if "no_overlapping_appointments" in error_str:
            raise HTTPException(409, "Horário já está ocupado")

        if "unique_idempotency_per_company" in error_str:
            raise HTTPException(400, "Requisição duplicada")

        raise HTTPException(400, "Erro ao criar agendamento")

    except Exception:
        db.rollback()
        raise


# =========================
# CHANGE STATUS
# =========================
def change_appointment_status(
    db: Session,
    appointment_id: UUID,
    new_status: str,
    current_user,
    note: str | None = None
):
    try:
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id
        ).first()

        if not appointment:
            raise HTTPException(404, "Agendamento não encontrado")

        current_status = appointment.status
        current_version = appointment.version

        if new_status not in ALLOWED_TRANSITIONS.get(current_status, []):
            raise HTTPException(
                400,
                f"Transição inválida: {current_status} → {new_status}"
            )

        # 🔒 Regra cancelamento
        if new_status == "cancelled":
            now = datetime.now(timezone.utc)
            is_admin = getattr(current_user, "is_admin", False)

            if not is_admin and appointment.start_at < now + timedelta(hours=2):
                raise HTTPException(
                    400,
                    "Cancelamento permitido somente com 2h de antecedência"
                )

        update_data = {
            "status": new_status,
            "version": current_version + 1
        }

        # 💰 Financeiro + cancelamento
        if new_status == "cancelled":
            if appointment.financial_status == "paid":
                update_data["financial_status"] = "refunded"
            else:
                update_data["financial_status"] = "cancelled"

            update_data["cancelled_at"] = datetime.now(timezone.utc)
            update_data["cancelled_by"] = current_user.id

        updated = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id,
            Appointment.version == current_version
        ).update(update_data)

        if updated == 0:
            raise HTTPException(409, "Conflito de concorrência, tente novamente")

        # 🧾 Log
        db.add(AppointmentStatusLog(
            company_id=appointment.company_id,
            appointment_id=appointment.id,
            from_status=current_status,
            to_status=new_status,
            changed_by=current_user.id,
            note=note
        ))

        db.commit()
        db.refresh(appointment)
        return appointment

    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(400, "Erro ao atualizar agendamento")

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise


# =========================
# RESCHEDULE
# =========================
def reschedule_appointment(
    db: Session,
    appointment_id: UUID,
    new_start_at: datetime,
    current_user
):
    try:
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id
        ).first()

        if not appointment:
            raise HTTPException(404, "Agendamento não encontrado")

        if appointment.status in ["completed", "cancelled", "no_show"]:
            raise HTTPException(400, "Agendamento não pode ser remarcado")

        if new_start_at.tzinfo is None:
            new_start_at = new_start_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        if new_start_at < now + timedelta(minutes=30):
            raise HTTPException(
                400,
                "Remarcação deve ter pelo menos 30 minutos de antecedência"
            )

        duration = int(
            (appointment.end_at - appointment.start_at).total_seconds() / 60
        )

        new_end_at = new_start_at + timedelta(minutes=duration)

        # 🔥 Disponibilidade
        available_slots = generate_available_slots(
            db=db,
            professional_id=appointment.professional_id,
            company_id=appointment.company_id,
            target_date=new_start_at.date(),
            duration_minutes=duration,
            exclude_appointment_id=appointment.id
        )

        available_slots_dt = [
            datetime.fromisoformat(slot) for slot in available_slots
        ]

        if new_start_at not in available_slots_dt:
            raise HTTPException(400, "Horário inválido ou indisponível")

        current_version = appointment.version
        old_start = appointment.start_at

        updated = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id,
            Appointment.version == current_version
        ).update({
            "start_at": new_start_at,
            "end_at": new_end_at,
            "version": current_version + 1
        })

        if updated == 0:
            raise HTTPException(409, "Conflito de concorrência, tente novamente")

        # 🧾 Log com contexto
        db.add(AppointmentStatusLog(
            company_id=appointment.company_id,
            appointment_id=appointment.id,
            from_status=appointment.status,
            to_status=appointment.status,
            changed_by=current_user.id,
            note=f"Rescheduled from {old_start} to {new_start_at}"
        ))

        db.commit()

        return db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id
        ).first()

    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(400, "Erro ao remarcar agendamento")

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise
