"""
main.py — CLI entrypoint for the Artech RBAC-aware RAG system

Usage:
    python src/main.py --role <role> --user-id <user_id> --query "<question>"

Examples:
    python src/main.py --role employee --user-id emp_001 --query "What is my leave balance?"
    python src/main.py --role admin --user-id admin_001 --query "What was Q3 revenue?"
    python src/main.py --role auditor --user-id aud_001 --query "Show me the NDA terms"
    python src/main.py --role manager --user-id mgr_001 --query "What does the employment contract say about IP?"

Interactive mode (no --query flag):
    python src/main.py --role employee --user-id emp_001
"""

import argparse
import sys
from pathlib import Path

from config import VALID_ROLES, VECTORSTORE_PATH
from chain import load_vectorstore, run_query


def parse_args():
    parser = argparse.ArgumentParser(
        description="Artech Solutions — RBAC-Aware RAG Knowledge Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Roles and permissions:
  admin     → Finance: Full | Legal: Full    | HR: Full
  manager   → Finance: Full | Legal: Summary | HR: Full
  employee  → Finance: None | Legal: None    | HR: Own records only
  auditor   → Finance: Full | Legal: Full    | HR: None

Examples:
  python src/main.py --role employee --user-id emp_001 --query "What is my leave balance?"
  python src/main.py --role manager --user-id mgr_001 --query "What are the NDA terms?"
  python src/main.py --role admin   --user-id adm_001 --query "What was our Q3 profit?"
        """,
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=VALID_ROLES,
        help="User role (admin|manager|employee|auditor)",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        dest="user_id",
        help="User identifier (e.g. emp_001, mgr_005, adm_001)",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Question to ask (omit for interactive mode)",
    )
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="Suppress retrieval trace; print only the final answer",
    )
    return parser.parse_args()


def check_vectorstore():
    """Ensure the vectorstore has been created before running queries."""
    vs_path = Path(VECTORSTORE_PATH)
    if not vs_path.exists() or not any(vs_path.iterdir()):
        print("ERROR: Vector store not found.")
        print("Run ingestion first:  python src/ingest.py")
        sys.exit(1)


def interactive_loop(vectorstore, role: str, user_id: str, verbose: bool):
    """Run an interactive query loop."""
    print(f"\nArtech RAG — Interactive Mode")
    print(f"Role: {role} | User ID: {user_id}")
    print("Type your question and press Enter. Type 'exit' to quit.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not query:
            continue
        if query.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            break

        run_query(vectorstore, role, user_id, query, verbose=verbose)


def main():
    args = parse_args()
    check_vectorstore()

    print(f"Loading vector store...")
    vectorstore = load_vectorstore()

    verbose = not args.no_trace

    if args.query:
        run_query(vectorstore, args.role, args.user_id, args.query, verbose=verbose)
    else:
        interactive_loop(vectorstore, args.role, args.user_id, verbose=verbose)


if __name__ == "__main__":
    main()
