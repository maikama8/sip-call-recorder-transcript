"""SQLAlchemy tables."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CallRow(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    uniqueid: Mapped[str | None] = mapped_column(String(64), index=True)
    linkedid: Mapped[str | None] = mapped_column(String(64), index=True)
    caller: Mapped[str | None] = mapped_column(String(64), index=True)
    callee: Mapped[str | None] = mapped_column(String(80), index=True)
    caller_name: Mapped[str | None] = mapped_column(String(128))
    direction: Mapped[str | None] = mapped_column(String(32), index=True)
    dcontext: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    billsec: Mapped[float | None] = mapped_column(Float)
    disposition: Mapped[str | None] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(16))
    source_path: Mapped[str | None] = mapped_column(String(1024), unique=True)
    audio_path: Mapped[str | None] = mapped_column(String(1024))
    language: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text, default="")
    transcript_text: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32), default="fake")
    notice: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="transcribed")
    created_at: Mapped[datetime] = mapped_column(DateTime)

    segments: Mapped[list["SegmentRow"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="SegmentRow.position",
        lazy="selectin",
    )


class SegmentRow(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(64))
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)

    call: Mapped[CallRow] = relationship(back_populates="segments")
