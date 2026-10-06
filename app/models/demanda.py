from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EstadoDemanda, in_check

if TYPE_CHECKING:
    from app.models.organizacion import Area, Empresa, Usuario
    from app.models.proyecto import Proyecto


class SolicitudDemanda(Base):
    __tablename__ = "solicitud_demanda"
    __table_args__ = (in_check("estado_demanda", EstadoDemanda, "estado_demanda"),)

    id_solicitud: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_usuario_solicitante: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    id_empresa: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("empresa.id_empresa", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    id_area: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("area.id_area", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    descripcion_necesidad: Mapped[str] = mapped_column(Text)
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    estado_demanda: Mapped[str] = mapped_column(String(50), default=EstadoDemanda.SOLICITADO.value, index=True)

    usuario_solicitante: Mapped[Usuario] = relationship(back_populates="solicitudes")
    empresa: Mapped[Empresa] = relationship(back_populates="solicitudes")
    area: Mapped[Area] = relationship(back_populates="solicitudes")
    proyecto: Mapped[Proyecto | None] = relationship(back_populates="solicitud", uselist=False)
