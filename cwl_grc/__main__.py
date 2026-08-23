"""Standalone entry: ``python -m cwl_grc`` or the ``cwl-grc`` console script."""

from __future__ import annotations

import uvicorn

from cwl_grc.app import create_app
from cwl_grc.remote_access import loopback_server_bind


def main() -> None:
    """Serve the local preview on loopback, requiring TLS when Keyverse is required."""
    settings = loopback_server_bind()
    uvicorn.run(create_app(), **settings)


if __name__ == "__main__":  # pragma: no cover
    main()
