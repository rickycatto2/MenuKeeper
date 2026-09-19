import os
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, JSON, Integer, Text, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATA = Path(os.environ.get('DATA_DIR', './data'))
for folder in ('originals', 'images', 'diagnostics'):
    (DATA / folder).mkdir(parents=True, exist_ok=True)
engine = create_engine('sqlite:///' + str(DATA / 'app.db'), connect_args={'check_same_thread': False, 'timeout': 30})
@event.listens_for(engine, 'connect')
def pragmas(db, _):
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
Session = sessionmaker(engine)
def now():
    return datetime.now(timezone.utc).isoformat()
class Base(DeclarativeBase):
    pass
class RecipeRow(Base):
    __tablename__ = 'recipes'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(String, default='home', index=True)
    body: Mapped[dict] = mapped_column(JSON)
    search_text: Mapped[str] = mapped_column(Text, default='')
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)
class HistoryRow(Base):
    __tablename__ = 'history'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[str] = mapped_column(String, index=True)
    date: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
class ConversionRow(Base):
    __tablename__ = 'conversions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[dict] = mapped_column(JSON)
