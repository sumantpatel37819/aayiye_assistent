"""
continue_chat.py — Session chat history manage karta hai.

- In-memory chat history rakho
- Follow-up queries context ke saath bhejo
- "exit" ya "q" pe session khatam karo
"""


class ChatSession:
    """Ek conversation session — history maintain karta hai."""

    def __init__(self):
        self.history: list = []   # [{"role": "user"/"assistant", "content": "..."}]

    def add_user(self, message: str):
        self.history.append({"role": "user", "content": message})

    def add_assistant(self, message: str):
        self.history.append({"role": "assistant", "content": message})

    def get_history(self) -> list:
        return self.history.copy()

    def clear(self):
        self.history = []
        print("🗑 Chat history clear ho gayi.")

    def print_history(self):
        if not self.history:
            print("(Koi chat history nahi hai abhi.)")
            return
        print("\n─── Chat History ───")
        for msg in self.history:
            role = "🧑 Aap" if msg["role"] == "user" else "🤖 Raja"
            print(f"{role}: {msg['content']}")
        print("─────────────────────")


def is_exit_command(text: str) -> bool:
    """User ne session khatam karna chaha?"""
    return text.strip().lower() in {"exit", "q", "quit", "band karo", "bye"}


def is_clear_command(text: str) -> bool:
    """User ne history clear karni chahi?"""
    return text.strip().lower() in {"clear", "reset", "naya", "new chat"}


def is_history_command(text: str) -> bool:
    """User ne history dekhni chahi?"""
    return text.strip().lower() in {"history", "purani baat", "past"}
