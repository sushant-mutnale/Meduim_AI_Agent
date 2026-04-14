from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base

class RunLog(Base):
    __tablename__ = "run_logs"
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="in_progress") # in_progress, completed, failed, paused
    error_message = Column(Text, nullable=True)
    
    drafts = relationship("Draft", back_populates="run")

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("run_logs.id"))
    query = Column(String, index=True)
    cluster_name = Column(String, index=True)
    momentum_score = Column(Float, default=0.0)
    relevance_score = Column(Float, default=0.0)
    competition_score = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0)
    is_selected = Column(Boolean, default=False)
    ranking_reason = Column(Text, nullable=True)

class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("run_logs.id"))
    topic_id = Column(Integer, ForeignKey("topics.id"))
    
    title = Column(String)
    subtitle = Column(String, nullable=True)
    body = Column(Text)
    
    confidence_score = Column(Float)
    review_notes = Column(JSON, nullable=True)
    is_approved = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    run = relationship("RunLog", back_populates="drafts")

class Publication(Base):
    __tablename__ = "publications"
    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"))
    medium_post_id = Column(String, unique=True, index=True)
    url = Column(String)
    published_at = Column(DateTime, default=datetime.utcnow)

class MemoryLog(Base):
    __tablename__ = "memory_logs"
    id = Column(Integer, primary_key=True, index=True)
    topic_name = Column(String, index=True)
    performance_status = Column(String)
    lessons_learned = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
