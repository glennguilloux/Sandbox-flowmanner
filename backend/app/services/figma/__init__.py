"""Figma integration service — REST API client for Figma design files."""

from .figma_client import FigmaAPIError, FigmaClient

__all__ = ["FigmaAPIError", "FigmaClient"]
