"""
rbac.py — Role-Based Access Control filter for RAG pipeline

Layer 1 of the RBAC enforcement:
- Filters retrieved LangChain Documents based on role permissions and user_id
- Logs what was dropped for audit/Task 3 evidence
"""

import logging
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_community.vectorstores import Chroma

from config import PERMISSIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def rbac_filter(
    docs: List[Document],
    role: str,
    user_id: str,
) -> Tuple[List[Document], List[Document]]:
    """
    Filter retrieved documents based on role permissions.

    Returns:
        allowed_docs: Documents the role is permitted to see
        dropped_docs: Documents that were filtered out (for audit logging)
    """
    allowed = []
    dropped = []

    for doc in docs:
        meta = doc.metadata
        dept = meta.get("department", "")
        access_level = meta.get("access_level", "full")
        doc_employee_id = meta.get("employee_id", "")

        # Get permission level for this role + department
        role_perms = PERMISSIONS.get(role, {})
        permission = role_perms.get(dept, "none")

        if permission == "none":
            logger.info(
                f"[RBAC DROP] role={role} has no access to dept={dept} "
                f"| source={meta.get('source_file', '?')}"
            )
            dropped.append(doc)

        elif permission == "full":
            allowed.append(doc)

        elif permission == "summary":
            # Only pass summary-tagged chunks; drop full-detail chunks
            if access_level == "summary":
                allowed.append(doc)
            else:
                logger.info(
                    f"[RBAC DROP] role={role} summary-only access to dept={dept}, "
                    f"dropping access_level=full chunk | source={meta.get('source_file', '?')}"
                )
                dropped.append(doc)

        elif permission == "own_only":
            # Only pass chunks belonging to this specific employee
            if doc_employee_id == user_id:
                allowed.append(doc)
            else:
                logger.info(
                    f"[RBAC DROP] role={role} own-only access to dept={dept}, "
                    f"dropping chunk for employee_id={doc_employee_id} "
                    f"(requesting user={user_id}) | source={meta.get('source_file', '?')}"
                )
                dropped.append(doc)

        else:
            # Unknown permission — default deny
            logger.warning(f"[RBAC DROP] Unknown permission '{permission}' — denying by default")
            dropped.append(doc)

    logger.info(
        f"[RBAC SUMMARY] role={role} user_id={user_id} | "
        f"retrieved={len(docs)} | allowed={len(allowed)} | dropped={len(dropped)}"
    )
    return allowed, dropped


class RBACRetriever(BaseRetriever):
    """
    LangChain-compatible retriever that wraps ChromaDB and applies RBAC filtering.

    This is Layer 1 of RBAC enforcement — hard metadata-based filtering
    before any context reaches the LLM.
    """

    vectorstore: Chroma
    role: str
    user_id: str
    k: int = 8

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(self, query: str) -> List[Document]:
        """Retrieve top-K docs from Chroma, then apply RBAC filter."""
        raw_docs = self.vectorstore.similarity_search(query, k=self.k)
        allowed_docs, dropped_docs = rbac_filter(raw_docs, self.role, self.user_id)

        if not allowed_docs:
            logger.info(f"[RBAC] No permitted documents found for role={self.role} query='{query[:60]}'")

        return allowed_docs

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return self._get_relevant_documents(query)
