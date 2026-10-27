"""Terminal interface for BuddyAI Phase 1."""

from __future__ import annotations

from agent.buddy_agent import BuddyAgent
from agent.personality import InvalidPersonalityError
from config import ConfigurationError, ModelConfig
from models.base_model import ModelError
from models.model_factory import create_model

HELP_TEXT = """Commands:
  /help                    Show this help
  /personality <name>      Set chill, playful, supportive, or thoughtful
  /reset                   Clear this session's conversation history
  /model                   Show the configured local runtime and model
  /exit                    Exit BuddyAI"""


def _print_header(config: ModelConfig, agent: BuddyAgent) -> None:
    print("=" * 36)
    print("        BuddyAI Companion")
    print("=" * 36)
    print(f"Runtime: {config.runtime}")
    print(f"Model: {config.model}")
    print(f"Personality: {agent.personality_name.title()}")
    print("Type /help for commands. Conversation history stays in RAM.\n")


def _handle_command(command: str, agent: BuddyAgent, config: ModelConfig) -> bool:
    """Handle a slash command. Return False when the CLI should exit."""

    parts = command.split()
    name = parts[0].lower()
    if name == "/exit" and len(parts) == 1:
        return False
    if name == "/help" and len(parts) == 1:
        print(HELP_TEXT)
    elif name == "/reset" and len(parts) == 1:
        agent.reset_conversation()
        print("Buddy: Conversation reset.")
    elif name == "/model" and len(parts) == 1:
        print(
            f"Buddy: Runtime={config.runtime}, model={config.model}, endpoint={config.base_url}"
        )
    elif name == "/personality" and len(parts) == 2:
        try:
            agent.set_personality(parts[1])
            print(f"Buddy: Personality changed to {agent.personality_name.title()}.")
        except InvalidPersonalityError as exc:
            print(f"Buddy: {exc}")
    else:
        print(
            "Buddy: Unknown or incomplete command. Type /help for available commands."
        )
    return True


def run_cli(config: ModelConfig | None = None) -> None:
    config = config or ModelConfig.from_env()
    agent = BuddyAgent(create_model(config), history_turns=config.history_turns)
    _print_header(config, agent)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBuddy: Bye for now!")
            break
        if not user_input:
            print("Buddy: Please type a message, or /help for commands.")
            continue
        if user_input.startswith("/"):
            if not _handle_command(user_input, agent, config):
                print("Buddy: Bye for now!")
                break
            continue
        try:
            print(f"Buddy: {agent.respond(user_input)}")
        except ModelError as exc:
            print(f"Buddy: I couldn't contact the local model. {exc}")


def main() -> int:
    try:
        run_cli()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
