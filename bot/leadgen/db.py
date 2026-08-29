"""Доступ до БД для модуля лідогенерації."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Lead, LeadKeyword, LeadPlatform, LeadSource


# ---------- Ключові слова ----------

async def add_keyword(session: AsyncSession, phrase: str) -> LeadKeyword | None:
    phrase = phrase.strip().lower()
    if not phrase:
        return None
    existing = await session.execute(
        select(LeadKeyword).where(LeadKeyword.phrase == phrase)
    )
    keyword = existing.scalar_one_or_none()
    if keyword is not None:
        keyword.is_active = True
        await session.commit()
        return keyword
    keyword = LeadKeyword(phrase=phrase)
    session.add(keyword)
    await session.commit()
    await session.refresh(keyword)
    return keyword


async def get_active_keywords(session: AsyncSession) -> list[LeadKeyword]:
    result = await session.execute(
        select(LeadKeyword).where(LeadKeyword.is_active.is_(True)).order_by(LeadKeyword.phrase)
    )
    return list(result.scalars().all())


async def deactivate_keyword(session: AsyncSession, keyword_id: int) -> bool:
    keyword = await session.get(LeadKeyword, keyword_id)
    if keyword is None:
        return False
    keyword.is_active = False
    await session.commit()
    return True


# ---------- Джерела (канали/групи) ----------

async def add_source(
    session: AsyncSession, identifier: str, platform: LeadPlatform = LeadPlatform.telegram
) -> LeadSource:
    source = LeadSource(identifier=identifier.strip(), platform=platform)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def get_active_sources(
    session: AsyncSession, platform: LeadPlatform | None = None
) -> list[LeadSource]:
    query = select(LeadSource).where(LeadSource.is_active.is_(True))
    if platform is not None:
        query = query.where(LeadSource.platform == platform)
    result = await session.execute(query.order_by(LeadSource.added_at))
    return list(result.scalars().all())


async def deactivate_source(session: AsyncSession, source_id: int) -> bool:
    source = await session.get(LeadSource, source_id)
    if source is None:
        return False
    source.is_active = False
    await session.commit()
    return True


async def set_source_chat_id(
    session: AsyncSession, source_id: int, chat_id: int, title: str | None = None
) -> None:
    source = await session.get(LeadSource, source_id)
    if source is None:
        return
    source.platform_chat_id = chat_id
    if title:
        source.title = title
    await session.commit()


# ---------- Знайдені ліди ----------

async def save_lead(
    session: AsyncSession,
    source_id: int,
    keyword_id: int,
    platform_message_id: str,
    text_snippet: str,
    message_link: str | None = None,
    author_username: str | None = None,
) -> Lead:
    lead = Lead(
        source_id=source_id,
        keyword_id=keyword_id,
        platform_message_id=platform_message_id,
        text_snippet=text_snippet[:1000],
        message_link=message_link,
        author_username=author_username,
    )
    session.add(lead)
    await session.commit()
    await session.refresh(lead)
    return lead


async def get_recent_leads(session: AsyncSession, limit: int = 10) -> list[Lead]:
    result = await session.execute(
        select(Lead)
        .options(selectinload(Lead.source), selectinload(Lead.keyword))
        .order_by(Lead.found_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_leads_since(session: AsyncSession, since: datetime) -> list[Lead]:
    result = await session.execute(
        select(Lead)
        .options(selectinload(Lead.source), selectinload(Lead.keyword))
        .where(Lead.found_at >= since)
        .order_by(Lead.found_at.desc())
    )
    return list(result.scalars().all())


async def get_leads_last_24h(session: AsyncSession) -> list[Lead]:
    return await get_leads_since(session, datetime.utcnow() - timedelta(hours=24))
