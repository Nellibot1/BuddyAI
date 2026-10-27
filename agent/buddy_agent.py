"""High-level controller that coordinates BuddyAI components."""

from __future__ import annotations

from agent.conversation_manager import ConversationManager
from agent.personality import PersonalityManager
from agent.prompt_builder import AgentContext, PromptBuilder
from models.base_model import BaseModel


class BuddyAgent:
    """Runtime-independent public interface for one BuddyAI session."""

    def __init__(
        self,
        model: BaseModel,
        personality: str = "chill",
        history_turns: int = 10,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self.model = model
        self.personality = PersonalityManager(personality)
        self.conversation = ConversationManager(history_turns)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self._system_prompt = self._build_system_prompt()

    @property
    def personality_name(self) -> str:
        return self.personality.name

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def respond(self, user_message: str, context: AgentContext | None = None) -> str:
        """Generate and remember a response; failed calls do not alter history."""

        clean_message = user_message.strip()
        if not clean_message:
            raise ValueError("Please enter a non-empty message.")
        system_prompt = (
            self._system_prompt
            if context is None
            else self.prompt_builder.build(
                self.personality.name, self.personality.instructions, context
            )
        )
        model_user_message = self.prompt_builder.build_user_message(
            clean_message, context.personal_memories if context else ()
        )
        messages = self.conversation.build_messages(system_prompt, model_user_message)
        response = self.model.generate(messages)
        self.conversation.add_turn(clean_message, response)
        return response

    def set_personality(self, personality: str) -> None:
        self.personality.set(personality)
        self._system_prompt = self._build_system_prompt()

    def reset_conversation(self) -> None:
        self.conversation.reset()

    def _build_system_prompt(self) -> str:
        return self.prompt_builder.build(
            self.personality.name, self.personality.instructions
        )
