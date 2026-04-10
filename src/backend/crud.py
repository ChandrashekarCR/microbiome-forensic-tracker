# This file contains all the functions needed to talk to the database
# CRUD operations with async/await support

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Samples


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


async def update_sample_status(db: AsyncSession, sample_id: str, status: str, error_msg: str = None):
    """
    UPDATE sample status
    Eg.
        await update_sample_status(db, sample_id, "running")
        await update_sample_status(db, sample_id, "pass")
        await update_sample_status(db, sample_id, "fail", error_msg="Pipeline crashed")
    """

    stmt = select(Samples).where(Samples.id == sample_id)
    result = await db.execute(stmt)
    sample = result.scalars().first()

    if not sample:
        return None

    sample.status = status
    if error_msg:
        sample.error_msg = error_msg

    await db.commit()
    await db.refresh(sample)
    return sample
