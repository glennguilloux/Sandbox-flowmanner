#!/usr/bin/env python3
"""
FastAPI middleware for Traefik integration.

This file is kept for backward compatibility but no longer provides
rate limiting functionality. Traefik handles rate limiting at the edge.
"""

import logging

logger = logging.getLogger(__name__)

# This module is deprecated - rate limiting is handled by Traefik
logger.info("Traefik integration middleware - rate limiting disabled, using Traefik only")
