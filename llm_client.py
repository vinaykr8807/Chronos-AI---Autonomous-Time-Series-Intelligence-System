"""
LLMClient — simple wrapper around OpenAI-compatible client.
Works with Gemini via the compatibility endpoint.
"""

from __future__ import annotations

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """
    Thin wrapper that creates an OpenAI-compatible client
    pointing at Gemini's endpoint.

    All agents receive a shared instance of this.
    """

    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=os.environ.get("GEMINI_API_KEY"),
            base_url=os.environ.get("GEMINI_BASE_URL"),
        )

    @property
    def raw(self):
        """Direct access to the underlying OpenAI client."""
        return self.client