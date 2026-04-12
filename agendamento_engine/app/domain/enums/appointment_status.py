from enum import Enum


class AppointmentStatus(str, Enum):
    SCHEDULED   = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"
    NO_SHOW     = "NO_SHOW"

    @property
    def is_terminal(self) -> bool:
        return self in (
            AppointmentStatus.COMPLETED,
            AppointmentStatus.CANCELLED,
            AppointmentStatus.NO_SHOW,
        )

    @property
    def allowed_transitions(self) -> set:
        """Retorna os estados para os quais esta transição é válida."""
        return _ALLOWED_TRANSITIONS.get(self, set())


# Definido fora da classe para evitar que o Enum trate como membro
_ALLOWED_TRANSITIONS: dict = {
    AppointmentStatus.SCHEDULED: {
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    },
    AppointmentStatus.IN_PROGRESS: {
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
    },
    AppointmentStatus.COMPLETED:  set(),
    AppointmentStatus.CANCELLED:  set(),
    AppointmentStatus.NO_SHOW:    set(),
}
