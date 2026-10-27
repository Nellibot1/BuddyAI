"""Construction helpers for runtime-independent model adapters."""

from config import ModelConfig
from models.base_model import BaseModel
from models.local_model import LocalOpenAIModel


def create_model(config: ModelConfig) -> BaseModel:
    """Create the adapter selected by configuration.

    All supported Phase 1 runtimes expose the same OpenAI-compatible contract,
    so they share one carefully validated adapter.
    """

    return LocalOpenAIModel(config)
