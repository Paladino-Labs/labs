import uuid
from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class ProductSale(Base, TimestampMixin):
    """
    Venda avulsa de produto para retirada na barbearia.

    Estados:
      RESERVED  — cliente escolheu p/ pagar e retirar no local (sem pgto online)
      PURCHASED — cliente pagou online, aguardando retirada
      PICKED_UP — retirado pelo cliente (ciclo encerrado)

    Compra AVULSA — sem vínculo a agendamento (appointment_id ausente
    por decisão de produto). A notificação de pendência (Sprint C)
    verifica se há venda não retirada em qualquer conclusão de
    agendamento do cliente.
    """
    __tablename__ = "product_sales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payments.payment_id", ondelete="SET NULL"),
        nullable=True,  # RESERVED não tem pagamento ainda
    )

    # Snapshots (sobrevivem a mudança/deleção do produto)
    product_name = Column(String(255), nullable=False)
    quantity     = Column(Integer, nullable=False, default=1)
    unit_price   = Column(Numeric(10, 2), nullable=False)  # snapshot
    total_price  = Column(Numeric(10, 2), nullable=False)

    # RESERVED | PURCHASED | PICKED_UP
    status = Column(String(20), nullable=False, default="RESERVED", index=True)

    picked_up_at = Column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer")
    product  = relationship("Product")
    payment  = relationship("Payment")
