"""Standalone entry: ``python -m cwl_grc`` or the ``cwl-grc`` console script."""

from __future__ import annotations

import os

import uvicorn

from cwl_grc.app import create_app


def main() -> None:
    """Serve the unauthenticated developer preview on loopback and $PORT."""
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
