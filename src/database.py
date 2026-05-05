from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, create_engine
from sqlalchemy.orm import sessionmaker
from pgvector.sqlalchemy import Vector
import datetime
from src.config import settings
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Food(Base):
    __tablename__ = "foods"
    __table_args__ = {"schema": "nutrition"}
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    portion_size_g = Column(Numeric(10, 2))
    calories = Column(Numeric(10, 2))
    protein_g = Column(Numeric(10, 2))
    carbs_g = Column(Numeric(10, 2))
    fat_g = Column(Numeric(10, 2))
    fiber_g = Column(Numeric(10, 2))
    sodium_mg = Column(Numeric(10, 2))
    water_g = Column(Numeric(10, 2))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = {"schema": "nutrition"}
    
    id = Column(Integer, primary_key=True)
    source = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384))
    page_number = Column(Integer)
    chunk_index = Column(Integer)
    language = Column(String, nullable=True) # Adiciona isto
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Setup engine
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)

def get_session():
    """Context manager para DB sessions"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def init_db():
    """Cria tabelas se não existirem"""
    Base.metadata.create_all(bind=engine)
    
if __name__ == "__main__":
    print("A estabelecer ligação à base de dados...")
    try:
        init_db()
        print("Tabelas criadas ou já existentes no esquema 'nutrition'!")
    except Exception as e:
        print(f"Erro ao criar base de dados: {e}")