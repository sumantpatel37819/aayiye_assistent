"""
gui_main.py — Vibrant Colorful Desktop GUI for Aayie AI Assistant
Supports 2-panel layout (Chat + Live Logs), Pause/Resume/Stop controls, Progress Bar, log syntax highlighting, and full intent feature parity.
"""

import asyncio
import os
import sys
import threading
import queue
import re
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

# Windows terminal UTF-8 print fix
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from Query_process.continue_chat import ChatSession, is_clear_command, is_exit_command, is_history_command
from Query_process.query_index import handle_query
from agent.router import classify_intent
from agent.code_generator import generate_code
from agent.safe_executor import execute_code
from agent.tools.weather_tool import get_weather
from agent.tools.sheets_tool import execute_sheets_instruction
from agent.tools.sheet_enricher_tool import enrich_state_places
from agent.tools.sheet_repair_tool import repair_state_places
from agent.tools.json_sync_tool import run_json_sync
from agent.task_controller import task_controller
from index_main import handle_chat, extract_enrich_params, WORKSPACE_DIR

# ─────────────────────────────────────────────
# Thread-safe stdout/stderr Log Redirector
# ─────────────────────────────────────────────

class LogRedirector:
    def __init__(self, log_queue, original_stream):
        self.log_queue = log_queue
        self.original_stream = original_stream

    def write(self, text):
        if text:
            self.log_queue.put(text)
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except Exception:
                pass

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass


# ─────────────────────────────────────────────
# Vibrant Main GUI Application Class
# ─────────────────────────────────────────────

class AayieGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🤖 Aayie AI Assistant — Desktop Dashboard")
        self.geometry("1150x720")
        self.minsize(950, 580)

        # 🎨 Rich Vibrant Color Palette
        self.BG_MAIN        = "#0f111a"  # Deep midnight violet
        self.BG_PANEL       = "#16192b"  # Sleek card background
        self.BG_TEXT        = "#0b0c10"  # Text display dark surface
        self.FG_TEXT        = "#e2e8f0"  # Crisp clean text
        
        self.COLOR_PURPLE   = "#c084fc"  # Electric Purple
        self.COLOR_CYAN     = "#38bdf8"  # Neon Cyan
        self.COLOR_GREEN    = "#4ade80"  # Mint Green
        self.COLOR_PINK     = "#f472b6"  # Vibrant Pink
        self.COLOR_AMBER    = "#fbbf24"  # Warm Gold/Amber
        self.COLOR_RED      = "#f87171"  # Coral Red
        
        self.BTN_PURPLE     = "#9333ea"  # Send button
        self.BTN_ORANGE     = "#ea580c"  # Pause button
        self.BTN_GREEN      = "#059669"  # Resume button
        self.BTN_RED        = "#dc2626"  # Stop button
        self.BTN_CYAN       = "#0891b2"  # Clear logs button

        self.configure(bg=self.BG_MAIN)
        self._setup_styles()

        self.session = ChatSession()
        self.log_queue = queue.Queue()
        self.is_processing = False

        # Redirect stdout and stderr
        sys.stdout = LogRedirector(self.log_queue, sys.__stdout__)
        sys.stderr = LogRedirector(self.log_queue, sys.__stderr__)

        # Build UI Layout
        self._build_ui()

        # Register task controller callback
        task_controller.register_callback(self._on_task_progress)

        # Start log queue polling loop
        self.after(100, self._poll_log_queue)

        print("✨ Aayie High-Aesthetics GUI initialized!")
        self._append_chat("Aayie", "Namaste! Main aapka AI Personal Assistant Aayie hoon. 🤖✨\n\n"
                                  "Main Web Search, Weather, Google Sheets, File Management aur Tourist Places Sheet Enrichment kar sakta hoon.\n\n"
                                  "💬 Koi bhi query type karein (e.g. 'Bihar ke all places fill karo')!")

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=self.BG_MAIN, foreground=self.FG_TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.BG_MAIN)
        style.configure("Panel.TFrame", background=self.BG_PANEL)
        
        style.configure("TLabelframe", background=self.BG_PANEL, foreground=self.COLOR_PURPLE, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=self.BG_PANEL, foreground=self.COLOR_PURPLE, font=("Segoe UI", 10, "bold"))

        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=6, background="#1e2238", foreground="#ffffff", borderwidth=0)
        style.map("TButton", background=[("active", "#2d3250")], foreground=[("active", "#ffffff")])

        style.configure("Send.TButton", background=self.BTN_PURPLE, foreground="#ffffff")
        style.map("Send.TButton", background=[("active", "#7e22ce")])

        style.configure("Pause.TButton", background=self.BTN_ORANGE, foreground="#ffffff")
        style.map("Pause.TButton", background=[("active", "#c2410c")])

        style.configure("Resume.TButton", background=self.BTN_GREEN, foreground="#ffffff")
        style.map("Resume.TButton", background=[("active", "#047857")])

        style.configure("Stop.TButton", background=self.BTN_RED, foreground="#ffffff")
        style.map("Stop.TButton", background=[("active", "#b91c1c")])

        style.configure("Clear.TButton", background=self.BTN_CYAN, foreground="#ffffff")
        style.map("Clear.TButton", background=[("active", "#0e7490")])

        style.configure("Vibrant.Horizontal.TProgressbar", thickness=16, troughcolor="#1e2238", background=self.COLOR_CYAN)

    def _build_ui(self):
        # Top Header Banner
        header = tk.Frame(self, bg="#1e1b2e", height=55, highlightbackground=self.COLOR_PURPLE, highlightthickness=1)
        header.pack(fill="x", side="top", padx=12, pady=(10, 6))

        title_lbl = tk.Label(
            header, 
            text="🤖  AAYIE  —  AI Personal Assistant Dashboard", 
            font=("Segoe UI", 14, "bold"), 
            bg="#1e1b2e", 
            fg=self.COLOR_PURPLE
        )
        title_lbl.pack(side="left", padx=16, pady=10)

        self.status_badge = tk.Label(
            header,
            text="🟢 SYSTEM ONLINE",
            font=("Segoe UI", 9, "bold"),
            bg="#064e3b",
            fg="#6ee7b7",
            padx=12,
            pady=4
        )
        self.status_badge.pack(side="right", padx=16)

        # Paned Window Splitter (Left Chat, Right Logs)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=12, pady=4)

        # ── LEFT PANEL: COLORFUL CHAT INTERFACE ─────────────
        left_frame = ttk.LabelFrame(paned, text=" 💬 Interactive Chat ", style="TLabelframe")
        paned.add(left_frame, weight=5)

        self.chat_display = ScrolledText(
            left_frame, 
            wrap="word", 
            bg=self.BG_TEXT, 
            fg=self.FG_TEXT, 
            insertbackground="white",
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
            state="disabled",
            relief="flat"
        )
        self.chat_display.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        
        # Color tags for Chat
        self.chat_display.tag_configure("user_hdr", foreground=self.COLOR_CYAN, font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("user_msg", foreground="#e0f2fe", font=("Segoe UI", 10))
        self.chat_display.tag_configure("ai_hdr", foreground=self.COLOR_GREEN, font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("ai_msg", foreground="#ecfdf5", font=("Segoe UI", 10))
        self.chat_display.tag_configure("sys_hdr", foreground=self.COLOR_AMBER, font=("Segoe UI", 9, "bold"))
        self.chat_display.tag_configure("sys_msg", foreground="#fef3c7", font=("Segoe UI", 9, "italic"))

        # Input Frame
        input_frame = tk.Frame(left_frame, bg=self.BG_PANEL)
        input_frame.pack(fill="x", padx=8, pady=8)

        self.entry_input = tk.Entry(
            input_frame, 
            bg="#1e2238", 
            fg="#ffffff", 
            insertbackground="white",
            font=("Segoe UI", 11),
            relief="flat",
            highlightbackground=self.COLOR_PURPLE,
            highlightthickness=1
        )
        self.entry_input.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)
        self.entry_input.bind("<Return>", lambda event: self._send_message())

        btn_send = ttk.Button(input_frame, text="Send 📤", style="Send.TButton", command=self._send_message)
        btn_send.pack(side="right")

        # ── RIGHT PANEL: SYNTAX HIGHLIGHTED LOGS ────────────
        right_frame = ttk.LabelFrame(paned, text=" 📜 Live System & Terminal Logs ", style="TLabelframe")
        paned.add(right_frame, weight=5)

        self.log_display = ScrolledText(
            right_frame, 
            wrap="word", 
            bg="#08090d", 
            fg="#94a3b8", 
            insertbackground="white",
            font=("Consolas", 9),
            padx=10,
            pady=10,
            state="disabled",
            relief="flat"
        )
        self.log_display.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        # Syntax tags for Logs
        self.log_display.tag_configure("log_success", foreground=self.COLOR_GREEN)
        self.log_display.tag_configure("log_error", foreground=self.COLOR_RED)
        self.log_display.tag_configure("log_warn", foreground=self.COLOR_AMBER)
        self.log_display.tag_configure("log_info", foreground=self.COLOR_CYAN)
        self.log_display.tag_configure("log_purple", foreground=self.COLOR_PURPLE)

        log_btn_frame = tk.Frame(right_frame, bg=self.BG_PANEL)
        log_btn_frame.pack(fill="x", padx=8, pady=6)

        btn_clear_logs = ttk.Button(log_btn_frame, text="Clear Logs 🧹", style="Clear.TButton", command=self._clear_logs)
        btn_clear_logs.pack(side="left")

        # ── BOTTOM PANEL: VIBRANT CONTROLS & PROGRESS ─────────
        bottom_frame = ttk.LabelFrame(self, text=" 🎛️ Live Task Control Panel ", style="TLabelframe")
        bottom_frame.pack(fill="x", side="bottom", padx=12, pady=(4, 10))

        ctrl_box = tk.Frame(bottom_frame, bg=self.BG_PANEL)
        ctrl_box.pack(fill="x", padx=10, pady=8)

        self.btn_pause = ttk.Button(ctrl_box, text="⏸ PAUSE", style="Pause.TButton", command=self._on_pause_click)
        self.btn_pause.pack(side="left", padx=(0, 6))

        self.btn_resume = ttk.Button(ctrl_box, text="▶ RESUME", style="Resume.TButton", command=self._on_resume_click)
        self.btn_resume.pack(side="left", padx=6)

        self.btn_stop = ttk.Button(ctrl_box, text="⏹ STOP", style="Stop.TButton", command=self._on_stop_click)
        self.btn_stop.pack(side="left", padx=6)

        self.lbl_task_status = tk.Label(
            ctrl_box, 
            text="Status: Ready | Task: Idle", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.BG_PANEL, 
            fg=self.COLOR_CYAN
        )
        self.lbl_task_status.pack(side="left", padx=16)

        self.progress_bar = ttk.Progressbar(ctrl_box, orient="horizontal", mode="determinate", style="Vibrant.Horizontal.TProgressbar")
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(10, 0))

    # ─────────────────────────────────────────────
    # UI Actions & Logging
    # ─────────────────────────────────────────────

    def _append_chat(self, sender: str, text: str):
        self.chat_display.config(state="normal")
        if sender == "User":
            self.chat_display.insert("end", f"🧑 Aap:\n", "user_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n\n", "user_msg")
        elif sender == "Aayie":
            self.chat_display.insert("end", f"🤖 Aayie:\n", "ai_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n\n", "ai_msg")
        else:
            self.chat_display.insert("end", f"⚙ {sender}:\n", "sys_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n\n", "sys_msg")

        self.chat_display.see("end")
        self.chat_display.config(state="disabled")

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self._insert_colored_log(msg)
            except queue.Empty:
                break
        self.after(100, self._poll_log_queue)

    def _insert_colored_log(self, msg: str):
        self.log_display.config(state="normal")
        
        # Color matching rules
        if any(w in msg for w in ["✅", "Successfully", "Completed", "Done"]):
            tag = "log_success"
        elif any(w in msg for w in ["❌", "Error", "Failed", "Exception"]):
            tag = "log_error"
        elif any(w in msg for w in ["⚠️", "⚠", "PAUSED", "Waiting"]):
            tag = "log_warn"
        elif any(w in msg for w in ["🔍", "Intent", "Processing", "Fetch"]):
            tag = "log_purple"
        else:
            tag = "log_info"

        self.log_display.insert("end", msg, tag)
        self.log_display.see("end")
        self.log_display.config(state="disabled")

    def _clear_logs(self):
        self.log_display.config(state="normal")
        self.log_display.delete("1.0", "end")
        self.log_display.config(state="disabled")

    def _send_message(self):
        query = self.entry_input.get().strip()
        if not query or self.is_processing:
            return

        self.entry_input.delete(0, "end")
        self._append_chat("User", query)

        # Special commands
        if is_exit_command(query):
            self.destroy()
            return
        if is_clear_command(query):
            self.session.clear()
            self._append_chat("System", "Chat history saaf ho gayi.")
            return
        if is_history_command(query):
            h_str = "\n".join([f"{m['role']}: {m['content']}" for m in self.session.get_history()])
            self._append_chat("System", f"History:\n{h_str}")
            return
        if query.lower() in ["pause", "p"]:
            self._on_pause_click()
            return
        if query.lower() in ["resume", "r"]:
            self._on_resume_click()
            return

        self.is_processing = True
        self.status_badge.config(text="⚡ PROCESSING", bg="#854d0e", fg="#fef08a")
        self.lbl_task_status.config(text="Status: Thinking / Executing... ⏳", fg=self.COLOR_AMBER)

        # Run query in background thread
        threading.Thread(target=self._async_worker, args=(query,), daemon=True).start()

    def _async_worker(self, user_input: str):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._process_query(user_input))
        except Exception as e:
            print(f"❌ Error executing query: {e}")
            self.after(0, self._append_chat, "System", f"Error: {e}")
        finally:
            self.is_processing = False
            self.after(0, self.status_badge.config, {"text": "🟢 SYSTEM ONLINE", "bg": "#064e3b", "fg": "#6ee7b7"})
            self.after(0, self.lbl_task_status.config, {"text": "Status: Ready | Task: Idle", "fg": self.COLOR_CYAN})

    async def _process_query(self, user_input: str):
        history_str = ""
        for msg in self.session.get_history()[-6:]:
            role = "Aap" if msg["role"] == "user" else "Aayie"
            history_str += f"{role}: {msg['content']}\n"

        print(f"\n🔍 [GUI] Intent classify ho raha hai...")
        lower_input = user_input.lower()
        if "json" in lower_input and ("update" in lower_input or "sync" in lower_input or "karo" in lower_input or "check" in lower_input or "file" in lower_input):
            intent = "SYNC_JSON"
        elif ("filter" in lower_input or "repair" in lower_input or "fix" in lower_input or "theek" in lower_input or "clean" in lower_input) and ("sheet" in lower_input or "places" in lower_input or "data" in lower_input):
            intent = "REPAIR_SHEET"
        elif ("enrich" in lower_input or "daalo" in lower_input or "fill" in lower_input or "bharo" in lower_input) and ("sheet" in lower_input):
            intent = "ENRICH_SHEET"
        else:
            intent = classify_intent(user_input)
        print(f"  📌 Intent: {intent}")

        self.session.add_user(user_input)

        if intent == "CHAT":
            print("💬 Direct jawab de raha hoon...")
            answer = handle_chat(user_input, history_str)
            self.session.add_assistant(answer)
            self.after(0, self._append_chat, "Aayie", answer)

        elif intent == "WEB_SEARCH":
            print("🌐 Web Search chal raha hai...")
            result = await handle_query(user_input, self.session.get_history())
            self.session.add_assistant(result["answer"])
            ans_text = result["answer"]
            if result.get("images"):
                ans_text += "\n\n📷 Images found:\n" + "\n".join(result["images"][:5])
            self.after(0, self._append_chat, "Aayie", ans_text)

        elif intent == "WEATHER":
            print("🌤 Weather fetch ho raha hai...")
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_ollama.llms import OllamaLLM
            _loc_model = OllamaLLM(model="llama3.2", keep_alive=-1)
            loc_prompt = ChatPromptTemplate.from_template("Extract ONLY the city/location name from this query. Reply with just the location name, nothing else.\n\nQuery: {q}\n\nLocation:")
            location = (loc_prompt | _loc_model).invoke({"q": user_input}).strip()
            weather_result = get_weather(location)
            self.session.add_assistant(weather_result)
            self.after(0, self._append_chat, "Aayie", f"Weather for {location}:\n{weather_result}")

        elif intent == "GOOGLE_SHEETS":
            print("📊 Google Sheets operation chal raha hai...")
            sheet_result = execute_sheets_instruction(user_input)
            self.session.add_assistant(str(sheet_result))
            self.after(0, self._append_chat, "Aayie", f"Sheets Result:\n{sheet_result}")

        elif intent == "ENRICH_SHEET":
            print("📝 Sheet Enrichment pipeline chal raha hai...")
            state, city = extract_enrich_params(user_input)
            if not state:
                msg = "Could not understand state name. Please specify state clearly (e.g., 'Bihar ke places fill karo')."
                self.after(0, self._append_chat, "Aayie", msg)
                return

            if hasattr(enrich_state_places, "invoke"):
                res_msg = enrich_state_places.invoke({"state_name": state, "city_name": city})
            else:
                res_msg = enrich_state_places(state_name=state, city_name=city)

            self.session.add_assistant(str(res_msg))
            self.after(0, self._append_chat, "Aayie", f"Enrichment Completed:\n{res_msg}")

        elif intent == "REPAIR_SHEET":
            print("🛠 Sheet Repair pipeline chal raha hai...")
            state, city = extract_enrich_params(user_input)
            if not state:
                msg = "Could not understand state to repair. Specify a state (e.g. 'Bihar sheet repair karo')."
                self.after(0, self._append_chat, "Aayie", msg)
                return

            res_msg = repair_state_places(state_name=state, city_name=city)
            self.session.add_assistant(str(res_msg))
            self.after(0, self._append_chat, "Aayie", f"Sheet Repair Completed:\n{res_msg}")

        elif intent == "SYNC_JSON":
            print("🔄 JSON files sync chal raha hai...")
            res_msg = run_json_sync()
            self.session.add_assistant(str(res_msg))
            self.after(0, self._append_chat, "Aayie", f"JSON Sync Result:\n{res_msg}")

        elif intent == "SYSTEM_ACTION":
            print(f"🤖 System action chal raha hai: {user_input}")
            code = generate_code(task=user_input, cwd=WORKSPACE_DIR)
            if code:
                confirm = messagebox.askyesno("Code Execution Confirmation", f"Following code was generated:\n\n{code[:300]}...\n\nDo you want to run this script?")
                if confirm:
                    output = execute_code(code=code, cwd=WORKSPACE_DIR, auto_approve=True)
                    self.session.add_assistant(f"Executed code output:\n{output}")
                    self.after(0, self._append_chat, "Aayie", f"Executed System Script:\n{output}")
                else:
                    self.after(0, self._append_chat, "Aayie", "Execution cancelled by user.")
            else:
                self.after(0, self._append_chat, "Aayie", "Could not generate code for this system action.")

    # ─────────────────────────────────────────────
    # Task Control & Progress Callbacks
    # ─────────────────────────────────────────────

    def _on_pause_click(self):
        task_controller.pause()
        self.status_badge.config(text="⏸ PAUSED", bg="#854d0e", fg="#fef08a")
        self.lbl_task_status.config(text="Status: PAUSING after current item... ⏸️", fg=self.COLOR_AMBER)

    def _on_resume_click(self):
        task_controller.resume()
        self.status_badge.config(text="⚡ PROCESSING", bg="#854d0e", fg="#fef08a")
        self.lbl_task_status.config(text="Status: RESUMED & RUNNING ▶️", fg=self.COLOR_GREEN)

    def _on_stop_click(self):
        task_controller.stop()
        self.status_badge.config(text="⏹ STOPPED", bg="#991b1b", fg="#fca5a5")
        self.lbl_task_status.config(text="Status: STOPPED ⏹️", fg=self.COLOR_RED)
        self.progress_bar["value"] = 0

    def _on_task_progress(self, task_name: str, idx: int, total: int, item_name: str, status: str):
        def _update():
            if total > 0:
                pct = int((idx / total) * 100)
                self.progress_bar["value"] = pct
            else:
                pct = 0

            if status == "PAUSED":
                self.status_badge.config(text="⏸ PAUSED", bg="#854d0e", fg="#fef08a")
                self.lbl_task_status.config(text=f"⏸️ PAUSED at [{idx}/{total}] '{item_name}'", fg=self.COLOR_AMBER)
            elif status == "PAUSED_REQUESTED":
                self.status_badge.config(text="⏸ PAUSING...", bg="#854d0e", fg="#fef08a")
                self.lbl_task_status.config(text=f"⏸️ PAUSING after '{item_name}' finishes...", fg=self.COLOR_AMBER)
            elif status == "STOPPED":
                self.status_badge.config(text="⏹ STOPPED", bg="#991b1b", fg="#fca5a5")
                self.lbl_task_status.config(text=f"⏹️ STOPPED at [{idx}/{total}]", fg=self.COLOR_RED)
            elif status == "RUNNING":
                self.status_badge.config(text="⚡ PROCESSING", bg="#064e3b", fg="#6ee7b7")
                self.lbl_task_status.config(text=f"▶️ [{idx}/{total}] ({pct}%): {item_name}", fg=self.COLOR_GREEN)
            elif status == "STARTED":
                self.status_badge.config(text="🚀 STARTED", bg="#1e3a8a", fg="#93c5fd")
                self.lbl_task_status.config(text=f"🚀 Started {task_name} (0/{total})", fg=self.COLOR_PURPLE)

        self.after(0, _update)


if __name__ == "__main__":
    app = AayieGUI()
    app.mainloop()
