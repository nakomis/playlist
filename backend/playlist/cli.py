"""Command line: run the service, sync and analyse the library, render locally."""

from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from . import library
from .cache import Cache
from .config import Settings
from .jobs import JobManager, MixRequest


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="playlist")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="web API, MCP server and the mix worker")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--mcp-port", type=int, default=8001)

    sub.add_parser("sync", help="index the Plex libraries")

    a = sub.add_parser("analyse", help="analyse tracks not yet analysed")
    a.add_argument("--library", action="append")
    a.add_argument("--workers", type=int, default=2)
    a.add_argument("--limit", type=int)

    sc = sub.add_parser("scan", help="index a local folder (development, no Plex)")
    sc.add_argument("folder", type=Path)
    sc.add_argument("--library", default="Music")
    sc.add_argument("--genre")

    m = sub.add_parser("mix", help="plan and render a mix here and now")
    m.add_argument("--genre", action="append", default=[])
    m.add_argument("--library", action="append", default=[])
    m.add_argument("--minutes", type=float, default=30)
    m.add_argument("--single", action="store_true")
    m.add_argument("--seed", type=int)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    cache = Cache(settings.db_path)

    if args.cmd == "sync":
        print(library.sync_plex(settings, cache))
    elif args.cmd == "scan":
        print(library.scan_folder(args.folder, args.library, cache, args.genre), "tracks")
    elif args.cmd == "analyse":

        def show(n: int, total: int) -> None:
            if n % 25 == 0 or n == total:
                print(f"{n}/{total}", flush=True)

        print(
            library.analyse_pending(
                cache, args.library, workers=args.workers, limit=args.limit, progress=show
            )
        )
    elif args.cmd == "mix":
        jobs = JobManager(settings, cache)
        job = jobs.submit(
            MixRequest(
                genres=args.genre,
                duration_min=args.minutes,
                libraries=args.library,
                output="single" if args.single else "split",
                seed=args.seed,
            )
        )
        jobs.process(job)
        print(job.status, job.error or "", jobs.mix_dir(job.id))
        for f in job.files:
            print(f"  {f['name']}  {f['duration_s'] / 60:.1f} min")
    elif args.cmd == "serve":
        serve(settings, cache, args.host, args.port, args.mcp_port)


def serve(settings: Settings, cache: Cache, host: str, port: int, mcp_port: int) -> None:
    import uvicorn

    from .api import create_app
    from .mcp_server import create_mcp

    jobs = JobManager(settings, cache)
    jobs.purge_old()
    jobs.start()
    mcp = create_mcp(settings, cache, jobs, host=host, port=mcp_port)
    threading.Thread(
        target=lambda: mcp.run(transport="streamable-http"), daemon=True, name="mcp"
    ).start()
    uvicorn.run(create_app(settings, cache, jobs), host=host, port=port)


if __name__ == "__main__":
    main()
