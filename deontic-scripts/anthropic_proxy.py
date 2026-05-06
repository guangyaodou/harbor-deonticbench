#!/usr/bin/env python3
"""
Proxy that rewrites Anthropic-style auth to Authorization: Bearer <upstream-key>,
strips query params vLLM doesn't understand (e.g. ?beta=true), and streams responses.

Usage:
    python3 deontic-scripts/anthropic_proxy.py --upstream http://172.17.0.1:9009 --port 9010 --api-key token-abc123
"""
import argparse
import asyncio
import logging
from urllib.parse import urlencode, urlparse, parse_qs

from aiohttp import ClientSession, web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Query params that vLLM doesn't understand and should be stripped
_STRIP_PARAMS = {"beta"}


async def handle(request: web.Request, upstream: str, api_key: str, session: ClientSession) -> web.Response:
    # Always use the upstream API key — Claude Code may send its OAuth token instead
    headers = {"Authorization": f"Bearer {api_key}"}
    for k, v in request.headers.items():
        if k.lower() in ("x-api-key", "authorization", "host"):
            continue
        headers[k] = v

    # Strip query params vLLM doesn't understand (e.g. ?beta=true causes 401)
    qs = {k: v for k, v in parse_qs(urlparse(request.path_qs).query).items() if k not in _STRIP_PARAMS}
    path = request.path + (("?" + urlencode(qs, doseq=True)) if qs else "")
    url = upstream.rstrip("/") + path
    body = await request.read()

    if request.method == "POST":
        log.info("FORWARDING TO: %s", url)
        log.info("REQUEST BODY: %s", body.decode(errors="replace")[:2000])

    async with session.request(
        request.method, url, headers=headers, data=body, allow_redirects=False
    ) as resp:
        resp_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("transfer-encoding", "content-encoding")
        }
        log.info("%s %s -> %s", request.method, request.path_qs, resp.status)

        is_streaming = "text/event-stream" in resp.headers.get("Content-Type", "")

        if is_streaming:
            stream_resp = web.StreamResponse(status=resp.status, headers=resp_headers)
            await stream_resp.prepare(request)
            async for chunk in resp.content.iter_any():
                await stream_resp.write(chunk)
            await stream_resp.write_eof()
            return stream_resp

        resp_body = await resp.read()
        if resp.status >= 400:
            log.info("RESPONSE BODY: %s", resp_body.decode(errors="replace")[:2000])
        return web.Response(status=resp.status, headers=resp_headers, body=resp_body)


async def main(upstream: str, port: int, api_key: str) -> None:
    async with ClientSession() as session:
        app = web.Application()
        app.router.add_route("*", "/{path_info:.*}", lambda r: handle(r, upstream, api_key, session))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        log.info("Proxy listening on 0.0.0.0:%d -> %s (api-key: %s...)", port, upstream, api_key[:8])
        await asyncio.Event().wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", default="http://172.17.0.1:9009")
    parser.add_argument("--port", type=int, default=9010)
    parser.add_argument("--api-key", default="token-abc123", help="API key to use for upstream vLLM requests")
    args = parser.parse_args()
    asyncio.run(main(args.upstream, args.port, args.api_key))
