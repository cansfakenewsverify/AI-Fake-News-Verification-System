"""
Models package.
Models are imported on-demand by their respective modules
to avoid loading PostgreSQL-only dependencies (pgvector) when not needed.
"""
