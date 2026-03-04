# Defines what the malmo_db database tables looks like
# Each class is a table in the database

# Importing libraries
from sqlalchemy import Column, Integer, Float, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base

# Table 1: samples
# Tracks every sample uploaded by the users
class Samples(Base):
    __tablename__ = 'samples'

    id = Column(Integer,primary_key=True,index=True)
    sample_name = Column(String(200), index=True) # zr23059_100
    username = Column(String(100), index= True)
    email = Column(String(100))

    # File metadata
    r1_path = Column(String(500)) # the file path for forward read
    r2_path = Column(String(500)) # the file path for reverse read

    # Pipeiline status
    # pending -> processing -> completed/failed
    status = Column(String,default="pending")

    # Timestamps
    submitted_at = Column(DateTime(timezone=True), default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Log and error info
    log_path = Column(String, nullable=True)
    error_msg = Column(Text, nullable=True)

    # Relationship
    # This links sample to its abundance results, because one sample can have many abundance results
    results = relationship("AbundanceResult", back_populates="sample")

    def __repr__(self):
        """
        Return a string representation of this object for debugging and logging.

        The representation includes the object's sample_name and status attributes
        in the form "<Sample {sample_name} | {status}>". Returns a str.
        """
        return f"<Sample {self.sample_name} | {self.status}>"


# Table 2: abundance results
# Stores the output of the sankemake pipeline
# one row one one taxons abundane in on sample

class AbundanceResult(Base):
    __tablename__ = "abundance_results"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign key - links it back the samples table
    # Which sa,ple does this abudance table result belong to?
    sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)

    # Taxonomic classification data
    taxon_name = Column(String, nullable=False)
    taxon_id = Column(String, nullable=True)
    taxon_rank = Column(String, nullable=True)

    # Abundance values
    relative_abundance = Column(Float, nullable=False)
    
    created_at = Column(DateTime, server_default=func.now())

    # Relationship
    # Links back to the sample table
    sample = relationship("Samples", back_populates="results")

    def __repr__(self):
        return f"<AbundanceResult {self.taxon_name}: {self.relative_abundance}>"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True)