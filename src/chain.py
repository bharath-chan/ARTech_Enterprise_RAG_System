"""
chain.py — LangChain LCEL chain for RBAC-aware RAG

Assembles:
  RBACRetriever → format_context → ChatPromptTemplate → OllamaLLM → StrOutputParser

Also exposes run_query() which returns a rich result object
with retrieval trace for Task 2/3 documentation.
"""

from __future__ import annotations

from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    EMBEDDING_MODEL,
    VECTORSTORE_PATH,
    TOP_K,
)
from rbac import RBACRetriever, rbac_filter
from prompts import prompt_template, format_context


def load_vectorstore() -> Chroma:
    """Load the persisted ChromaDB vectorstore."""
    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    return Chroma(
        persist_directory=VECTORSTORE_PATH,
        embedding_function=embeddings,
        collection_name="artech_docs",
    )


def build_chain(vectorstore: Chroma, role: str, user_id: str):
    """
    Build the LCEL chain for a given role and user_id.

    Chain steps:
      1. RBACRetriever — retrieves top-K docs from Chroma, applies Layer 1 RBAC filter
      2. format_context — formats allowed docs into a context string
      3. prompt_template — injects system prompt + role + context + question
      4. llm — Qwen 2.5:3b via Ollama
      5. StrOutputParser — extracts string response
    """
    retriever = RBACRetriever(
        vectorstore=vectorstore,
        role=role,
        user_id=user_id,
        k=TOP_K,
    )

    llm = OllamaLLM(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        temperature=0.1,  # Low temp for factual, consistent answers
    )

    chain = (
        {
            "context": retriever | RunnableLambda(format_context),
            "question": RunnablePassthrough(),
            "role": RunnableLambda(lambda _: role),
            "user_id": RunnableLambda(lambda _: user_id),
        }
        | prompt_template
        | llm
        | StrOutputParser()
    )

    return chain


def run_query(
    vectorstore: Chroma,
    role: str,
    user_id: str,
    query: str,
    verbose: bool = True,
) -> dict:
    """
    Run a full RAG query and return a detailed result dict.

    Returns:
        {
            "role": str,
            "user_id": str,
            "query": str,
            "retrieved_chunks": List[Document],   # raw retrieval before RBAC
            "allowed_chunks": List[Document],      # after RBAC filter
            "dropped_chunks": List[Document],      # what was filtered out
            "context_injected": str,               # what LLM actually sees
            "response": str,                       # LLM final answer
        }
    """
    # --- Step 1: Raw retrieval (bypassing RBAC for trace visibility) ---
    raw_docs = vectorstore.similarity_search(query, k=TOP_K)

    # --- Step 2: Apply RBAC filter ---
    allowed_docs, dropped_docs = rbac_filter(raw_docs, role, user_id)

    # --- Step 3: Format context ---
    context = format_context(allowed_docs)

    # --- Step 4: Build and invoke chain ---
    chain = build_chain(vectorstore, role, user_id)
    response = chain.invoke(query)

    result = {
        "role": role,
        "user_id": user_id,
        "query": query,
        "retrieved_chunks": raw_docs,
        "allowed_chunks": allowed_docs,
        "dropped_chunks": dropped_docs,
        "context_injected": context,
        "response": response,
    }

    if verbose:
        _print_trace(result)

    return result


def _print_trace(result: dict):
    """Print a formatted trace of the query execution."""
    sep = "=" * 65

    print(f"\n{sep}")
    print(f"QUERY TRACE")
    print(f"{sep}")
    print(f"Role    : {result['role']}")
    print(f"User ID : {result['user_id']}")
    print(f"Query   : {result['query']}")

    print(f"\n--- Retrieved Chunks ({len(result['retrieved_chunks'])}) ---")
    for i, doc in enumerate(result["retrieved_chunks"], 1):
        m = doc.metadata
        print(
            f"  [{i}] dept={m.get('department','?')} | "
            f"access_level={m.get('access_level','?')} | "
            f"employee_id='{m.get('employee_id','?')}' | "
            f"source={m.get('source_file','?')}"
        )

    print(f"\n--- RBAC Filter: Allowed ({len(result['allowed_chunks'])}) ---")
    for i, doc in enumerate(result["allowed_chunks"], 1):
        m = doc.metadata
        print(f"  [✓] [{i}] dept={m.get('department','?')} | source={m.get('source_file','?')}")

    print(f"\n--- RBAC Filter: Dropped ({len(result['dropped_chunks'])}) ---")
    if result["dropped_chunks"]:
        for i, doc in enumerate(result["dropped_chunks"], 1):
            m = doc.metadata
            print(f"  [✗] [{i}] dept={m.get('department','?')} | source={m.get('source_file','?')}")
    else:
        print("  (none dropped)")

    print(f"\n--- Context Injected into LLM ---")
    if result["context_injected"]:
        print(result["context_injected"][:800] + ("..." if len(result["context_injected"]) > 800 else ""))
    else:
        print("  (empty — no permitted context found)")

    print(f"\n--- LLM Response ---")
    print(result["response"])
    print(f"{sep}\n")
