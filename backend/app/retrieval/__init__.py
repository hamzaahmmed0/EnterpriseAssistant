"""Permission-aware, self-correcting retrieval engine.

Importable and usable without the web layer: the API, the contract reviewer, and the MCP server
all depend on this package, and none of them may reach past it to the vector store directly.
"""
