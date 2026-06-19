"""Quick tablebase probe CLI."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.tablebase import probe


async def main(fen: str) -> int:
    p = await probe(fen)
    print(f"fen   : {p.fen}")
    print(f"pieces: {p.pieces}")
    print(f"wdl   : {p.wdl}")
    print(f"dtz   : {p.dtz}")
    print(f"verd. : {p.verdict}")
    print(f"src   : {p.source}")
    return 0


if __name__ == "__main__":
    fen = sys.argv[1] if len(sys.argv) > 1 else "4k3/8/8/8/8/8/4K3/4R3 w - - 0 1"
    raise SystemExit(asyncio.run(main(fen)))
