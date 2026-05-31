from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Document(Base):
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_hash = Column(String, unique=True, index=True, nullable=False) # SHA-256
    original_url = Column(String, nullable=False)
    portal_name = Column(String) # То, как файл назван на портале (кириллица)
    file_type = Column(String) # pdf, zip, rar, docx
    status = Column(String, default='NEW') # NEW, DOWNLOADED, SLICED, ERROR
    storage_uri = Column(String) # storage://...
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class CrawlerState(Base):
    __tablename__ = 'crawler_state'
    
    id = Column(Integer, primary_key=True)
    last_page = Column(Integer, default=1)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Инициализация подключения
engine = create_engine(os.getenv('DATABASE_URL'))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    print("База данных PostgreSQL успешно инициализирована.")
