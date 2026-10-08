"""
ingest.py — Document ingestion pipeline

Reads synthetic corpus documents, chunks them, embeds using
Ollama nomic-embed-text, and stores in ChromaDB
with RBAC metadata tags.

Run once before using main.py:
    python src/ingest.py
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import List

from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import EMBEDDING_MODEL, VECTORSTORE_PATH, OLLAMA_BASE_URL

CORPUS_DIR = Path(__file__).parent / "corpus"

# -------------------------------------------------------------------
# Text splitter config
# -------------------------------------------------------------------
splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=80,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def parse_header(text: str) -> dict:
    """Extract metadata from document header lines."""
    meta = {}
    for line in text.splitlines()[:8]:
        if line.startswith("DEPARTMENT:"):
            meta["department"] = line.split(":", 1)[1].strip()
        elif line.startswith("ACCESS LEVEL:"):
            raw = line.split(":", 1)[1].strip().lower()
            # Normalize
            if raw in ("full", "summary only", "own record only"):
                meta["access_level"] = "full" if raw == "full" else raw
            else:
                meta["access_level"] = "full"
        elif line.startswith("EMPLOYEE_ID:"):
            val = line.split(":", 1)[1].strip()
            meta["employee_id"] = "" if val.lower() in ("null", "none", "") else val
    return meta


def ingest_legal_document(filepath: Path, base_meta: dict) -> List[Document]:
    """
    Special handling for Legal documents.

    Legal docs contain a [SUMMARY SECTION] that gets its own chunk
    tagged access_level=summary. All other chunks are tagged access_level=full.
    """
    text = filepath.read_text(encoding="utf-8")

    # Extract summary section
    summary_match = re.search(
        r"\[SUMMARY SECTION — START\](.*?)\[SUMMARY SECTION — END\]",
        text,
        re.DOTALL,
    )

    docs = []

    if summary_match:
        summary_text = summary_match.group(1).strip()
        summary_doc = Document(
            page_content=summary_text,
            metadata={
                **base_meta,
                "access_level": "summary",
                "source_file": filepath.name,
                "chunk_type": "summary",
            },
        )
        docs.append(summary_doc)

        # Extract full document section (after SUMMARY SECTION END)
        full_text_start = text.find("[SUMMARY SECTION — END]") + len("[SUMMARY SECTION — END]")
        full_text = text[full_text_start:].strip()
    else:
        full_text = text

    # Chunk the full document
    chunks = splitter.split_text(full_text)
    for i, chunk in enumerate(chunks):
        docs.append(
            Document(
                page_content=chunk,
                metadata={
                    **base_meta,
                    "access_level": "full",
                    "source_file": filepath.name,
                    "chunk_type": "full",
                    "chunk_index": i,
                },
            )
        )

    return docs


def ingest_standard_document(filepath: Path, base_meta: dict) -> List[Document]:
    """Standard chunking for Finance and HR documents."""
    text = filepath.read_text(encoding="utf-8")
    chunks = splitter.split_text(text)

    docs = []
    for i, chunk in enumerate(chunks):
        docs.append(
            Document(
                page_content=chunk,
                metadata={
                    **base_meta,
                    "source_file": filepath.name,
                    "chunk_type": "full",
                    "chunk_index": i,
                },
            )
        )
    return docs


def load_corpus() -> List[Document]:
    """Load and process all corpus documents."""
    all_docs = []

    for filepath in sorted(CORPUS_DIR.glob("*.txt")):
        text = filepath.read_text(encoding="utf-8")
        base_meta = parse_header(text)
        base_meta.setdefault("department", "Unknown")
        base_meta.setdefault("access_level", "full")
        base_meta.setdefault("employee_id", "")

        dept = base_meta["department"]

        print(f"  Processing: {filepath.name} [dept={dept}]")

        if dept == "Legal":
            docs = ingest_legal_document(filepath, base_meta)
        else:
            docs = ingest_standard_document(filepath, base_meta)

        print(f"    → {len(docs)} chunks created")
        all_docs.extend(docs)

    return all_docs


def main():
    print("=" * 60)
    print("ARTECH RAG — Document Ingestion Pipeline")
    print("=" * 60)

    # Check corpus exists
    if not CORPUS_DIR.exists() or not list(CORPUS_DIR.glob("*.txt")):
        print(f"ERROR: No .txt files found in {CORPUS_DIR}")
        sys.exit(1)

    print(f"\n[1/3] Loading corpus from: {CORPUS_DIR}")
    docs = load_corpus()
    print(f"\n  Total chunks to embed: {len(docs)}")

    print(f"\n[2/3] Loading embedding model via Ollama: {EMBEDDING_MODEL}")
    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    print(f"\n[3/3] Creating ChromaDB at: {VECTORSTORE_PATH}")
    # Clear existing vectorstore if it exists
    vectorstore_path = Path(VECTORSTORE_PATH)
    if vectorstore_path.exists():
        shutil.rmtree(vectorstore_path)
        print("  Cleared existing vectorstore.")

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=VECTORSTORE_PATH,
        collection_name="artech_docs",
    )

    print(f"\n✓ Ingestion complete. {len(docs)} chunks stored in ChromaDB.")
    print(f"  Vector store path: {VECTORSTORE_PATH}")

    # Summary breakdown
    dept_counts = {}
    for doc in docs:
        d = doc.metadata.get("department", "Unknown")
        dept_counts[d] = dept_counts.get(d, 0) + 1
    print("\n  Chunks by department:")
    for dept, count in sorted(dept_counts.items()):
        print(f"    {dept}: {count} chunks")


if __name__ == "__main__":
    main()
