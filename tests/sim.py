"""Run the fake ProAmp8 as a real HTTP server (for screenshots / manual testing).

    python -m tests.sim --port 8090
"""

from __future__ import annotations

import argparse
import asyncio
import json

from aiohttp import web
from yarl import URL

from .conftest import FakeProAmp


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    a = ap.parse_args()
    amp = FakeProAmp()
    for z, (name, vol, pwr, mute) in enumerate([
        ("Kitchen", 42, 1, 0), ("Dining", 35, 1, 0), ("Lounge L/R", 55, 3, 0), ("Patio", 30, 2, 1),
        ("Master Bedroom", 25, 3, 0), ("Ensuite", 20, 3, 0), ("Gym", 60, 1, 0), ("Office", 0, 0, 0),
    ]):
        amp.zones[z].update(name=name, volume=vol, pwr=pwr, mute=mute)

    async def handler(request: web.Request) -> web.Response:
        body = await request.text() if request.can_read_body else None
        status, data = amp.handle(request.method, URL(str(request.url)), body)
        return web.Response(status=status, text=json.dumps(data), content_type="application/json")

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", a.port).start()
    print(f"Fake ProAmp8 on :{a.port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
