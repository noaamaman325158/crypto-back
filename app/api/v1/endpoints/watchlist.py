import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.database import get_db
from app.models.user import User
from app.repositories.crypto_repo import CryptoRepository
from app.repositories.watchlist_repo import WatchlistRepository
from app.schemas.watchlist import WatchlistAddRequest, WatchlistItemResponse, WatchlistResponse

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = WatchlistRepository(db)
    items = await repo.get_user_watchlist(current_user.id)
    return WatchlistResponse(items=items, total=len(items))


@router.post("", response_model=WatchlistItemResponse, status_code=201)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    crypto_repo = CryptoRepository(db)
    coin = await crypto_repo.get_by_id(body.cryptocurrency_id)
    if not coin:
        raise NotFoundError("Cryptocurrency not found")

    watchlist_repo = WatchlistRepository(db)
    existing = await watchlist_repo.get_item(current_user.id, body.cryptocurrency_id)
    if existing:
        raise ConflictError("Already in watchlist")

    item = await watchlist_repo.add(current_user.id, body.cryptocurrency_id)
    return item


@router.delete("/{cryptocurrency_id}", status_code=204)
async def remove_from_watchlist(
    cryptocurrency_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = WatchlistRepository(db)
    item = await repo.get_item(current_user.id, cryptocurrency_id)
    if not item:
        raise NotFoundError("Item not found in watchlist")
    await repo.remove(item)
