# Register a real-world client

Use this when the client already has real documents in a Mistral Document
Library and synthetic manufacturing is not required.

The developer needs these four values:

- Legal name
- Industry
- Geography
- Mistral Library ID

After the MCP server has been started once, add or update the client in
PostgreSQL:

```sql
INSERT INTO mcp_client_registry (
    legal_name,
    industry,
    geography,
    mistral_library_id
)
VALUES (
    'Example Manufacturing Private Limited',
    'Manufacturing',
    'India',
    'your-mistral-library-id'
)
ON CONFLICT (normalized_name) DO UPDATE SET
    legal_name = EXCLUDED.legal_name,
    industry = EXCLUDED.industry,
    geography = EXCLUDED.geography,
    mistral_library_id = EXCLUDED.mistral_library_id,
    updated_at = NOW();
```

Database rows do not require a service or page restart. The open New Deal page
refreshes the company list every 10 seconds and whenever the Legal name dropdown
is opened. Selecting it fills Industry and Geography. Creating the deal copies
the documents from the registered Mistral Library into that deal's working
library.

The same operation is also available through the MCP tool
`register_real_world_client`.
