import asyncio
from typing import Optional
from ..schemas.yahoo import MarketMoversResponse
from ..services.yahoo import get_market_movers

class MarketMoversState:
    def __init__(self):
        self._state: Optional[MarketMoversResponse] = None
        self._lock = asyncio.Lock()

    async def update(self, new_state: MarketMoversResponse):
        async with self._lock:
            self._state = new_state

    async def get(self) -> MarketMoversResponse:
        async with self._lock:
            if self._state is None:
                return MarketMoversResponse()
            return self._state

# Global instance to be used by the background task and API
market_movers_state = MarketMoversState()

async def run_market_movers_loop():
    while True:
        try:
            mm_data = await get_market_movers(count=10)
            await market_movers_state.update(mm_data)
        except Exception as e:
            print(f"[market_movers] Error fetching data: {e}")

        # Poll every 1 hour (3600 seconds)
        await asyncio.sleep(3600)
