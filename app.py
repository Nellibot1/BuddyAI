"""Local graphical entry point for BuddyAI Phase 2."""

from __future__ import annotations

from agent.application_controller import BuddyApplication
from config import ConfigurationError, ModelConfig, default_database_path
from memory.database import Database, DatabaseError
from models.model_factory import create_model


def create_application() -> BuddyApplication:
    config = ModelConfig.from_env()
    database = Database(default_database_path())
    return BuddyApplication(create_model(config), config, database)


def main() -> int:
    try:
        from ui.gradio_app import build_gradio_app

        application = create_application()
        demo = build_gradio_app(application)
        demo.queue(default_concurrency_limit=1).launch(
            server_name="127.0.0.1",
            share=False,
            show_api=False,
            show_error=False,
            inbrowser=True,
        )
    except ImportError:
        print("Gradio is not installed. Run: python -m pip install -r requirements.txt")
        return 2
    except (ConfigurationError, DatabaseError) as exc:
        print(f"BuddyAI could not start: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
