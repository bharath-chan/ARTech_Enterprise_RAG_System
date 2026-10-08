# config.py — RBAC permission matrix and system configuration

# Role-based access permissions per department
# Possible values: "full", "summary", "own_only", "none"
PERMISSIONS = {
    "admin":    {"Finance": "full",     "Legal": "full",    "HR": "full"},
    "manager":  {"Finance": "full",     "Legal": "summary", "HR": "full"},
    "employee": {"Finance": "none",     "Legal": "none",    "HR": "own_only"},
    "auditor":  {"Finance": "full",     "Legal": "full",    "HR": "none"},
}

VALID_ROLES = list(PERMISSIONS.keys())
DEPARTMENTS = ["Finance", "Legal", "HR"]

# Ollama config
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"

# Embedding model (Ollama nomic-embed-text)
EMBEDDING_MODEL = "nomic-embed-text"

# Chroma vector store path
VECTORSTORE_PATH = "./src/vectorstore"

# Retrieval config
TOP_K = 8  # retrieve more, RBAC filter will prune down
