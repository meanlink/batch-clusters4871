from sqlalchemy import String, JSON, Double, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Dataset(Base):
    __tablename__ = 'datasets'
    __table_args__ = (UniqueConstraint('origin_id', 'correction_key', name='uq_dataset_correction'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    records: Mapped[list] = mapped_column(JSON)
    raw_records: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    origin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correction_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Double)
