import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.documents import read_source, split_text  # noqa: E402
from app.settings import get_settings  # noqa: E402
from app.vector_store import EmbeddingService, get_chunk_store  # noqa: E402


def main() -> None:
    settings = get_settings()
    text = read_source(settings.source_path)
    chunks = split_text(text)
    embedder = EmbeddingService()
    vectors = embedder.embed_many(chunks)
    payloads = [{"id": f"chunk_{idx}", "text": chunk, "source": str(settings.source_path)} for idx, chunk in enumerate(chunks)]
    store = get_chunk_store()
    store.rebuild(vectors, payloads)
    print(f"Indexed {len(chunks)} chunks from {settings.source_path}")


if __name__ == "__main__":
    main()
