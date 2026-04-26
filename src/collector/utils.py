#!/usr/bin/env python3
"""Utility functions for NetOps."""

import logging
import os

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("netops")


def parse_snmp_oid(oid_str: str) -> str:
    """Parse SNMP OID string and extract the index."""
    # Extract last number from OID (the index)
    parts = oid_str.split(".")
    return parts[-1] if parts else ""
