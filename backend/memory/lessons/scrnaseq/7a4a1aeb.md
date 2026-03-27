---
id: 7a4a1aeb
source: agent
tags: [scimilarity, dependency-management, tiledb, workaround]
session_id: cd37b440-04e5-4dea-8f8c-f21d5800c2fc
created_at: 2026-03-26T14:18:34.382406
---

# TileDB Vector Search Stub Required for SCimilarity with HNSWLIB

SCimilarity has an optional dependency on tiledb.vector_search that can cause import failures even when using the HNSWLIB backend. Creating a stub module before importing SCimilarity resolves this: `import types; tiledb_stub = types.ModuleType('tiledb'); tiledb_stub.vector_search = types.ModuleType('tiledb.vector_search'); sys.modules['tiledb'] = tiledb_stub; sys.modules['tiledb.vector_search'] = tiledb_stub.vector_search`. This allows SCimilarity to load successfully without requiring the full TileDB installation, which is critical for containerized environments where dependencies must be minimal.
