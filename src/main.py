import asyncio

import xclient


async def stream_timeline():
    async with xclient.XTimelineClient(
        "curl.txt", persist_last_id_path="state/last_id.txt"
    ) as xc:
        async for t in xc.stream(interval_s=5.0):
            print(t.to_markdown())


if __name__ == "__main__":
    asyncio.run(stream_timeline())
