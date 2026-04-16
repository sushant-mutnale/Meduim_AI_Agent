from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base


class RunLog(Base):
    """
    PDF Step 10: Tracks each pipeline run end-to-end.
    Stores status, timing, and links to all artifacts produced.
    """
    __tablename__ = "run_logs"
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="in_progress") # in_progress, completed, failed, paused
    selected_topic = Column(String, nullable=True)
    final_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Run metadata
    tokens_used = Column(Integer, default=0)
    api_calls = Column(Integer, default=0)
    execution_time_seconds = Column(Float, nullable=True)
    
    drafts = relationship("Draft", back_populates="run")
    step_logs = relationship("StepLog", back_populates="run")


class Topic(Base):
    """
    PDF Step 10: Each discovered topic with full scoring breakdown.
    """
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("run_logs.id"))
    query = Column(String, index=True)
    cluster_name = Column(String, index=True)
    momentum_score = Column(Float, default=0.0)
    relevance_score = Column(Float, default=0.0)
    competition_score = Column(Float, default=0.0)
    source_diversity = Column(Integer, default=0)
    novelty_score = Column(Float, default=0.0)
    recency_score = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0)
    is_selected = Column(Boolean, default=False)
    ranking_reason = Column(Text, nullable=True)
    confidence_gap = Column(Float, nullable=True)


class ResearchClaim(Base):
    """
    PDF Step 10: Stores each validated/weak/rejected claim with provenance.
    Enables claim lineage tracking and contradiction audit.
    """
    __tablename__ = "research_claims"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("run_logs.id"))
    text = Column(Text)
    sources = Column(JSON)  # List of source strings
    confidence = Column(Float, default=0.0)
    status = Column(String, default="validated")  # validated, weak_valid, rejected
    is_weak = Column(Boolean, default=False)
    note = Column(Text, nullable=True)  # Warning note for weak claims
    created_at = Column(DateTime, default=datetime.utcnow)


class Draft(Base):
    """
    PDF Step 10: Stores article drafts with review scores.
    Supports multi-pass writing by storing each revision.
    """
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("run_logs.id"))
    topic_id = Column(Integer, ForeignKey("topics.id"))
    revision_number = Column(Integer, default=1)
    
    title = Column(String)
    subtitle = Column(String, nullable=True)
    body = Column(Text)
    
    # Multi-criteria review scores (PDF Step 10)
    clarity_score = Column(Float, nullable=True)
    depth_score = Column(Float, nullable=True)
    originality_score = Column(Float, nullable=True)
    trust_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    
    review_notes = Column(JSON, nullable=True)
    is_approved = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    run = relationship("RunLog", back_populates="drafts")


class Publication(Base):
    """Tracks what was published to Medium."""
    __tablename__ = "publications"
    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"))
    medium_post_id = Column(String, unique=True, index=True)
    url = Column(String)
    published_at = Column(DateTime, default=datetime.utcnow)


class MemoryLog(Base):
    """
    PDF Step 12: Memory / Learning Layer.
    Stores topic outcomes so the ranking agent can penalize repeated failures
    and improve future runs.
    """
    __tablename__ = "memory_logs"
    id = Column(Integer, primary_key=True, index=True)
    topic_name = Column(String, index=True)
    performance_status = Column(String)  # pass, failed, skipped
    lessons_learned = Column(Text)
    review_scores = Column(JSON, nullable=True)  # {clarity, depth, originality, trust}
    created_at = Column(DateTime, default=datetime.utcnow)


class StepLog(Base):
    """
    PDF Step 13: Per-step logging for debugging and auditing.
    Each pipeline step logs its status, timing, and any errors.
    """
    __tablename__ = "step_logs"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("run_logs.id"))
    step_name = Column(String, index=True)
    status = Column(String, default="started")  # started, success, failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    execution_time_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)  # Brief summary of what the step produced
    
    run = relationship("RunLog", back_populates="step_logs")
