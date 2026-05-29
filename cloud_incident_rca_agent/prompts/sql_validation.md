# SQL Validation

Generate SQL only from known schema context and a specific hypothesis. Queries
must be read-only, single statement, bounded by WHERE and LIMIT for row queries,
and include an interpretation rule.

Do not use SELECT *, mutation statements, transaction statements, stored
procedures, broad scans, or sensitive fields.
