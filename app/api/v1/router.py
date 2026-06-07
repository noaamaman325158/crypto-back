from fastapi import APIRouter

from app.api.v1.endpoints import auth, cryptocurrencies, insights, watchlist

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(cryptocurrencies.router)
router.include_router(watchlist.router)
router.include_router(insights.router)
