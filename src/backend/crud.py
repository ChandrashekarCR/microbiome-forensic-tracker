# This file contains all the functions needed to talk to the database
# CRUD operations with async/await support

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Abundance, Samples


# Create a new sample when the user uploads the fastq samples
async def create_sample(
    db: AsyncSession,
    username: str,
    email: str,
    sample_name: str,
    r1_path: str,
    r2_path: str,
) -> Samples:
    """
    INSERT a new sample into the database
    Returns the created Sample object
    """

    new_sample = Samples(
        username=username,
        email=email,
        sample_name=sample_name,
        r1_path=r1_path,
        r2_path=r2_path,
        status="pending",
    )

    db.add(new_sample)  # Stage the insert
    await db.commit()  # await the commit
    await db.refresh(new_sample)  # await the refresh (gets auto-generated id)
    return new_sample


# Get sample by name
async def get_sample_by_name(db: AsyncSession, sample_name: str) -> Samples:
    """
    SELECT sample WHERE sample_name = ?
    Return Sample object or None
    """
    # Use select() instead of .query()
    stmt = select(Samples).where(Samples.sample_name == sample_name)
    result = await db.execute(stmt)
    return result.scalars().first()


# Get sample by id
async def get_sample_by_id(db: AsyncSession, sample_id: str) -> Samples:
    """
    SELECT sample WHERE id = ?
    Return Sample object or None
    """
    stmt = select(Samples).where(Samples.id == sample_id)
    result = await db.execute(stmt)
    return result.scalars().first()


# Get all samples
async def get_all_samples(db: AsyncSession) -> list[Samples]:
    """
    SELECT all samples, newest first
    """
    stmt = select(Samples).order_by(Samples.submitted_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_sample_status(db: AsyncSession, sample_id: str, status: str, **kwargs):
    """
    UPDATE sample status
    Eg.
        await update_sample_status(db, sample_id, "running")
        await update_sample_status(db, sample_id, "completed")
        await update_sample_status(db, sample_id, "failed", error_msg="Pipeline crashed")
    """

    stmt = select(Samples).where(Samples.id == sample_id)
    result = await db.execute(stmt)
    sample = result.scalars().first()

    if not sample:
        return None

    sample.status = status

    for key, value in kwargs.items():
        if hasattr(sample, key) and value is not None:
            setattr(sample, key, value)

    await db.commit()
    await db.refresh(sample)
    return sample


async def delete_sample(db: AsyncSession, sample_name: str):
    """
    Delete a sample from the database by sample name.
    Returns True if deleted, False if not found.
    """
    stmt = select(Samples).where(Samples.sample_name == sample_name)
    result = await db.execute(stmt)
    sample = result.scalars().first()
    if not sample:
        return False

    await db.delete(sample)
    await db.commit()
    return True


async def update_celery_task_id(db: AsyncSession, sample_id: str, celery_task_id: str):
    """Store the Celery task UUID in the sample record for tracking."""
    stmt = select(Samples).where(Samples.id == sample_id)
    result = await db.execute(stmt)
    sample = result.scalars().first()
    if sample:
        sample.celery_task_id = celery_task_id
        await db.commit()
    return sample


async def fetch_abundance(db: AsyncSession, sample_name: str, rank: str) -> pd.DataFrame:
    stmt = select(Abundance).where(Abundance.sample_name == sample_name, Abundance.rank == rank)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise ValueError(f"No abundance data found for sample='{sample_name}' at rank='{rank}'. Has the pipeline completed for this sample?")

    # Build the long format of the dataframe first, because that is how it is stored in the database
    long_df = pd.DataFrame([{"clade": r.clade, "relative_abundance": r.relative_abundance} for r in rows])

    # Pivot the dataframe
    wide_df = long_df.set_index("clade")["relative_abundance"].to_frame().T.reset_index(drop=True)

    return wide_df
