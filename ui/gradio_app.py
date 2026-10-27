"""Gradio interface backed by one authoritative BuddyApplication instance."""

from __future__ import annotations

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

from agent.application_controller import BuddyApplication
from memory.database import DatabaseError
from models.base_model import ModelError

CSS = """
:root { --buddy-accent: #7357a6; --buddy-soft: #f5f0ff; }
.gradio-container { max-width: 1120px !important; margin: auto !important; }
#buddy-header { text-align: center; padding: 0.7rem 0 0.2rem; }
#buddy-header h1 { color: var(--buddy-accent); margin-bottom: 0.1rem; }
#privacy-note { background: #f8f7fb; border: 1px solid #e5e0ee; border-radius: 12px; padding: 0.7rem 1rem; }
.primary { background: var(--buddy-accent) !important; }
"""


def build_gradio_app(controller: BuddyApplication) -> gr.Blocks:
    """Build the local UI without launching or exposing a network server."""

    def memory_rows() -> list[list[object]]:
        return [
            [
                memory.id,
                memory.content,
                memory.memory_type,
                memory.updated_at[:10],
                memory.source,
            ]
            for memory in controller.list_memories()
        ]

    def memory_choices() -> list[tuple[str, int]]:
        return [
            (f"#{memory.id} · {memory.content[:72]}", memory.id)
            for memory in controller.list_memories()
        ]

    def send_message(message: str):
        try:
            result = controller.send_message(message)
            status = "✓ Response generated locally."
            if result.memories_saved:
                status += (
                    f" Automatically saved {result.memories_saved} memory record(s)."
                )
            if result.warning:
                status += f" Warning: {result.warning}"
            return (
                "",
                controller.chat_history,
                status,
                gr.update(
                    choices=controller.conversation_choices(),
                    value=controller.current_conversation_id,
                ),
                "**Status: 🟢 Connected — local inference succeeded.**",
                memory_rows(),
                gr.update(choices=memory_choices(), value=None),
            )
        except (ModelError, DatabaseError, ValueError) as exc:
            return (
                message,
                controller.chat_history,
                f"⚠️ {exc}",
                gr.update(),
                "**Status: 🔴 Local runtime unavailable or request failed.**",
                memory_rows(),
                gr.update(),
            )

    def start_new_conversation():
        controller.new_conversation()
        return (
            [],
            gr.update(value=None, choices=controller.conversation_choices()),
            "New conversation started.",
        )

    def clear_conversation():
        controller.clear_current_conversation()
        return (
            [],
            gr.update(value=None, choices=controller.conversation_choices()),
            "Current conversation cleared and its saved copy deleted.",
        )

    def open_conversation(conversation_id: int | None):
        if conversation_id is None:
            return controller.chat_history, "Choose a saved conversation."
        try:
            return controller.open_conversation(
                int(conversation_id)
            ), "Saved conversation opened."
        except (KeyError, ValueError, DatabaseError) as exc:
            return controller.chat_history, f"⚠️ {exc}"

    def delete_memory(memory_id: int | None):
        if memory_id is None:
            status = "⚠️ Select a memory to delete."
        else:
            try:
                deleted = controller.delete_memory(int(memory_id))
                status = "Memory deleted." if deleted else "Memory was already absent."
            except DatabaseError as exc:
                status = f"⚠️ {exc}"
        return (
            memory_rows(),
            gr.update(choices=memory_choices(), value=None),
            status,
        )

    def delete_all_memories(confirmed: bool):
        if not confirmed:
            return memory_rows(), gr.update(), "⚠️ Check the confirmation box first."
        try:
            count = controller.delete_all_memories()
            return (
                [],
                gr.update(choices=[], value=None),
                f"Deleted {count} saved memories.",
            )
        except DatabaseError as exc:
            return memory_rows(), gr.update(), f"⚠️ {exc}"

    def update_personality(name: str):
        try:
            controller.set_personality(name)
            return f"Personality changed to {controller.personality_name.title()}."
        except (ValueError, DatabaseError) as exc:
            return f"⚠️ {exc}"

    def update_name(name: str):
        try:
            saved_name = controller.set_buddy_name(name)
            return f"# 🧡 {saved_name}", f"Display name changed to {saved_name}."
        except (ValueError, DatabaseError) as exc:
            return gr.update(), f"⚠️ {exc}"

    def update_memory_enabled(enabled: bool):
        try:
            controller.set_memory_enabled(enabled)
            state = "enabled" if enabled else "disabled"
            return f"Automatic long-term memory {state}."
        except DatabaseError as exc:
            return f"⚠️ {exc}"

    def update_history_enabled(enabled: bool):
        try:
            controller.set_history_enabled(enabled)
            state = "enabled" if enabled else "disabled"
            return (
                [],
                gr.update(value=None, choices=controller.conversation_choices()),
                f"Persistent conversation history {state}; a new session was started.",
            )
        except DatabaseError as exc:
            return controller.chat_history, gr.update(), f"⚠️ {exc}"

    def delete_history(confirmed: bool):
        if not confirmed:
            return (
                controller.chat_history,
                gr.update(),
                "⚠️ Check the confirmation box first.",
            )
        try:
            count = controller.delete_all_conversations()
            return (
                [],
                gr.update(choices=[], value=None),
                f"Deleted {count} saved conversations.",
            )
        except DatabaseError as exc:
            return controller.chat_history, gr.update(), f"⚠️ {exc}"

    with gr.Blocks(
        css=CSS, title=f"{controller.buddy_name} · Local AI Companion"
    ) as demo:
        heading = gr.Markdown(f"# 🧡 {controller.buddy_name}", elem_id="buddy-header")
        gr.Markdown("A private companion powered by a language model on this computer.")

        with gr.Tabs():
            with gr.Tab("Chat"), gr.Row():
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        value=controller.chat_history,
                        label=controller.buddy_name,
                        height=510,
                        layout="bubble",
                        bubble_full_width=False,
                        placeholder="Start a conversation whenever you're ready.",
                    )
                    with gr.Row():
                        message_box = gr.Textbox(
                            placeholder=f"Message {controller.buddy_name}…",
                            show_label=False,
                            lines=2,
                            max_lines=6,
                            scale=5,
                        )
                        send_button = gr.Button("Send", variant="primary", scale=1)
                    chat_status = gr.Markdown(
                        "Ready. Messages are sent only to the configured local endpoint."
                    )
                with gr.Column(scale=1, min_width=250):
                    connection_status = gr.Markdown(
                        f"**Status: ⚪ Not checked**  \n"
                        "Sending a message verifies local inference.\n\n"
                        f"Runtime: `{controller.model_config.runtime}`  \n"
                        f"Model: `{controller.model_config.model}`  \n"
                        f"Endpoint: `{controller.model_config.base_url}`"
                    )
                    conversation_picker = gr.Dropdown(
                        choices=controller.conversation_choices(),
                        label="Previous conversations",
                        value=None,
                    )
                    open_button = gr.Button("Open selected")
                    new_button = gr.Button("New conversation")
                    clear_button = gr.Button(
                        "Clear current conversation", variant="secondary"
                    )

            with gr.Tab("What Buddy Knows About Me"):
                gr.Markdown(
                    "Buddy automatically extracts useful, non-sensitive facts after each successful interaction. You can inspect and delete any saved memory here."
                )
                memory_table = gr.Dataframe(
                    value=memory_rows(),
                    headers=["ID", "Memory", "Type", "Saved", "Source"],
                    datatype=["number", "str", "str", "str", "str"],
                    interactive=False,
                    wrap=True,
                    label="Automatically saved memories",
                )
                memory_picker = gr.Dropdown(
                    choices=memory_choices(), label="Select a memory to delete"
                )
                delete_memory_button = gr.Button("Delete selected", variant="stop")
                memory_status = gr.Markdown("Memory controls are ready.")

                with gr.Accordion("Delete all saved memories", open=False):
                    confirm_delete_memories = gr.Checkbox(
                        label="I understand this permanently deletes all saved memories"
                    )
                    delete_all_memories_button = gr.Button(
                        "Delete all memories", variant="stop"
                    )

            with gr.Tab("Companion"):
                personality = gr.Radio(
                    choices=["chill", "playful", "supportive", "thoughtful"],
                    value=controller.personality_name,
                    label="Personality",
                    info="Changes tone, but never replaces Buddy's safety and privacy boundaries.",
                )
                buddy_name = gr.Textbox(
                    value=controller.buddy_name,
                    label="Companion display name",
                    max_lines=1,
                )
                save_name_button = gr.Button("Save display name", variant="primary")
                companion_status = gr.Markdown(
                    "Personality and name are saved locally."
                )

                gr.Markdown(
                    "### Future webcam integration\n"
                    "Phase 2 does not access your camera. A future optional vision module may provide an explicitly uncertain structured cue to the existing agent context."
                )

            with gr.Tab("Privacy & Data"):
                gr.Markdown(
                    "**Personal memories** are automatically extracted facts used for personalization. "
                    "**Conversation history** is a reopenable copy of chat messages. "
                    "Deleting one does not delete the other.",
                    elem_id="privacy-note",
                )
                memory_enabled = gr.Checkbox(
                    value=controller.memory_enabled,
                    label="Enable automatic long-term memory creation and retrieval",
                )
                history_enabled = gr.Checkbox(
                    value=controller.history_enabled,
                    label="Save new conversation messages",
                )
                gr.Textbox(
                    value=str(controller.database.path),
                    label="Local data file",
                    interactive=False,
                )
                gr.Markdown(
                    f"Runtime: `{controller.model_config.runtime}` · Model: `{controller.model_config.model}`  \n"
                    "The SQLite file is local but is **not automatically encrypted**. Other people with device-level access may be able to read it. No public Gradio share is enabled."
                )
                privacy_status = gr.Markdown("Privacy controls are ready.")
                with gr.Accordion("Delete all conversation history", open=False):
                    confirm_delete_history = gr.Checkbox(
                        label="I understand this permanently deletes all saved messages"
                    )
                    delete_history_button = gr.Button(
                        "Delete conversation history", variant="stop"
                    )
                clear_session_button = gr.Button("Clear current in-memory session")

        send_outputs = [
            message_box,
            chatbot,
            chat_status,
            conversation_picker,
            connection_status,
            memory_table,
            memory_picker,
        ]
        send_button.click(send_message, message_box, send_outputs, concurrency_limit=1)
        message_box.submit(send_message, message_box, send_outputs, concurrency_limit=1)
        new_button.click(
            start_new_conversation,
            outputs=[chatbot, conversation_picker, chat_status],
            concurrency_limit=1,
        )
        clear_button.click(
            clear_conversation,
            outputs=[chatbot, conversation_picker, chat_status],
            concurrency_limit=1,
        )
        clear_session_button.click(
            start_new_conversation,
            outputs=[chatbot, conversation_picker, privacy_status],
            concurrency_limit=1,
        )
        open_button.click(
            open_conversation,
            conversation_picker,
            [chatbot, chat_status],
            concurrency_limit=1,
        )

        delete_memory_button.click(
            delete_memory,
            memory_picker,
            [memory_table, memory_picker, memory_status],
            concurrency_limit=1,
        )
        delete_all_memories_button.click(
            delete_all_memories,
            confirm_delete_memories,
            [memory_table, memory_picker, memory_status],
            concurrency_limit=1,
        )

        personality.change(
            update_personality, personality, companion_status, concurrency_limit=1
        )
        save_name_button.click(
            update_name,
            buddy_name,
            [heading, companion_status],
            concurrency_limit=1,
        )
        memory_enabled.change(
            update_memory_enabled,
            memory_enabled,
            privacy_status,
            concurrency_limit=1,
        )
        history_enabled.change(
            update_history_enabled,
            history_enabled,
            [chatbot, conversation_picker, privacy_status],
            concurrency_limit=1,
        )
        delete_history_button.click(
            delete_history,
            confirm_delete_history,
            [chatbot, conversation_picker, privacy_status],
            concurrency_limit=1,
        )

    return demo
