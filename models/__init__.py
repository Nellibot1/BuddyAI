"""Language-model adapters used by BuddyAI."""

from models.base_model import BaseModel, Message, ModelError
from models.local_model import LocalOpenAIModel

__all__ = ["BaseModel", "LocalOpenAIModel", "Message", "ModelError"]
