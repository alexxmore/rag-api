from pathlib import Path

from pypdf import PdfReader

from app.tokens import count_tokens


def read_source(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def split_text(text: str, chunk_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        if current and current_tokens + paragraph_tokens > chunk_tokens:
            chunks.append("\n\n".join(current))
            overlap: list[str] = []
            overlap_count = 0
            for item in reversed(current):
                item_tokens = count_tokens(item)
                if overlap_count + item_tokens > overlap_tokens:
                    break
                overlap.insert(0, item)
                overlap_count += item_tokens
            current = overlap
            current_tokens = overlap_count
        current.append(paragraph)
        current_tokens += paragraph_tokens

    if current:
        chunks.append("\n\n".join(current))
    return chunks
