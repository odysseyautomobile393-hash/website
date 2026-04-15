#!/usr/bin/env python3
"""
Database initialization script for Supabase PostgreSQL
This script creates the necessary tables in the Supabase database
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

# Supabase PostgreSQL settings
SUPABASE_HOST = 'db.zwlhdzpybfsqpmzcslhc.supabase.co'
SUPABASE_PORT = 5432
SUPABASE_USER = 'postgres'
SUPABASE_PASSWORD = 'Sayed$786'
SUPABASE_DB = 'postgres'

# SQLAlchemy database URL (PostgreSQL via psycopg2)
DATABASE_URL = f"postgresql+psycopg2://{SUPABASE_USER}:{SUPABASE_PASSWORD}@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DB}"

# Initialize SQLAlchemy
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=True)
Base = declarative_base()

# Define the models
class UserInfo(Base):
    __tablename__ = 'users_info'
    id = Column(Integer, primary_key=True)
    user_uuid = Column(String(64), unique=True, index=True)
    ip = Column(String(64))
    user_agent = Column(Text)
    device = Column(String(128))
    visits_count = Column(Integer, default=0)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)

class Referrer(Base):
    __tablename__ = 'referrers'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    count = Column(Integer, default=0)

class BlogPost(Base):
    __tablename__ = 'blog_posts'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    summary = Column(Text)
    details = Column(Text)
    img_urls = Column(Text)
    url = Column(String(1024))
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Create all tables in the database"""
    print("Creating tables in Supabase PostgreSQL...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully!")
        print("✓ Tables created:")
        print("  - users_info")
        print("  - referrers")
        print("  - blog_posts")
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False
    return True

if __name__ == '__main__':
    init_db()
