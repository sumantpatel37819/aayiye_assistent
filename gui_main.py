"""
gui_main.py — Ultra-Modern Obsidian & Cyber Dark Desktop GUI for Aayie AI Assistant
Features:
  - Harmonious, balanced Obsidian & Indigo/Slate color palette (high-contrast, professional, easy on the eyes)
  - Canvas-based Smooth Pill Buttons with true rounded corners and micro-hover interactions
  - Smooth Segmented Pill Mode Switcher (Aayie General vs Tour RAG Vector Engine)
  - macOS-Style Developer Console with traffic light controls (🔴 🟡 🟢)
  - Clean conversational message cards with soft border dividers
  - Smooth quick-action prompt chips
  - Refined live task controls (Pause / Resume / Stop) with live progress bar and telemetry
"""

import asyncio
import os
import sys
import threading
import queue
import re
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkinter import font as tkfont
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
# Canvas-based Smooth Rounded Pill Button
# ─────────────────────────────────────────────

class SmoothButton(tk.Canvas):
    """
    Genuine rounded pill button rendered via Canvas polygon smoothing.
    Provides silky hover animations, pressed feedback, and clean antialiased appearance.
    """
    def __init__(self, master, text="", command=None, bg_color="#6366F1", hover_color="#4F46E5",
                 active_color="#4338CA", text_color="#FFFFFF", font=("Segoe UI", 9, "bold"),
                 radius=9, width=None, height=30, parent_bg="#121520", border_color=None, 
                 border_width=1, padx=14, **kwargs):
        self.fnt = tkfont.Font(font=font)
        self.text = text
        req_w = width if width else (self.fnt.measure(text) + padx * 2)
        
        super().__init__(
            master, 
            width=req_w, 
            height=height, 
            bg=parent_bg, 
            highlightthickness=0, 
            bd=0,
            **kwargs
        )
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.active_color = active_color
        self.text_color = text_color
        self.border_color = border_color
        self.border_width = border_width
        self.radius = radius
        self.w = req_w
        self.h = height
        self.is_hovered = False

        self._draw(self.bg_color)
        
        # Interactive bindings
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(cursor="hand2")

    def _draw_round_rect(self, x1, y1, x2, y2, r, fill, outline):
        points = (
            x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1,
            x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
            x2, y2-r, x2, y2, x2-r, y2, x2-r, y2,
            x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
            x1, y2-r, x1, y1+r, x1, y1+r, x1, y1
        )
        return self.create_polygon(points, smooth=True, fill=fill, outline=outline or fill, width=self.border_width)

    def _draw(self, fill):
        self.delete("all")
        self._draw_round_rect(1, 1, self.w - 1, self.h - 1, self.radius, fill, self.border_color)
        self.create_text(self.w // 2, self.h // 2, text=self.text, fill=self.text_color, font=self.fnt)

    def _on_enter(self, event):
        self.is_hovered = True
        self._draw(self.hover_color)

    def _on_leave(self, event):
        self.is_hovered = False
        self._draw(self.bg_color)

    def _on_press(self, event):
        self._draw(self.active_color)

    def _on_release(self, event):
        if self.is_hovered:
            self._draw(self.hover_color)
            if self.command:
                self.command()
        else:
            self._draw(self.bg_color)

    def update_config(self, text=None, bg_color=None, hover_color=None, text_color=None, border_color=None):
        if text is not None:
            self.text = text
            self.w = self.fnt.measure(text) + 24
            self.configure(width=self.w)
        if bg_color is not None:
            self.bg_color = bg_color
        if hover_color is not None:
            self.hover_color = hover_color
        if text_color is not None:
            self.text_color = text_color
        if border_color is not None:
            self.border_color = border_color
        self._draw(self.bg_color)


# ─────────────────────────────────────────────
# Smooth Segmented Pill Mode Switcher
# ─────────────────────────────────────────────

class SmoothSegmentedSwitcher(tk.Frame):
    """Sleek segmented pill switcher with genuine rounded corners and accent highlights."""
    def __init__(self, master, options, current_val, on_change, bg="#121520", **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self.options = options  # list of (val, label, accent_color, hover_color)
        self.current_val = current_val
        self.on_change = on_change
        self.buttons = {}

        # Container pill frame
        self.pill_container = tk.Frame(self, bg="#181C2B", padx=3, pady=3, highlightbackground="#242B42", highlightthickness=1)
        self.pill_container.pack(side="left")

        for val, label, accent, accent_hover in self.options:
            btn = SmoothButton(
                self.pill_container,
                text=label,
                bg_color="#181C2B",
                hover_color="#22283D",
                active_color="#141825",
                text_color="#8E9AA8",
                radius=7,
                height=26,
                parent_bg="#181C2B",
                padx=10,
                command=lambda v=val: self._select(v)
            )
            btn.pack(side="left", padx=2)
            self.buttons[val] = (btn, accent, accent_hover)

        self._refresh_highlight()

    def _select(self, val):
        if self.current_val != val:
            self.current_val = val
            self._refresh_highlight()
            if self.on_change:
                self.on_change(val)

    def _refresh_highlight(self):
        for val, (btn, accent, accent_hover) in self.buttons.items():
            if val == self.current_val:
                btn.update_config(
                    bg_color=accent,
                    hover_color=accent_hover,
                    text_color="#FFFFFF"
                )
            else:
                btn.update_config(
                    bg_color="#181C2B",
                    hover_color="#22283D",
                    text_color="#8E9AA8"
                )

    def get(self):
        return self.current_val


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
# Ultra-Modern & Harmonious Aayie GUI
# ─────────────────────────────────────────────

class AayieGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aayie AI — Autonomous Agent & Tour RAG Dashboard")
        self.geometry("1200x760")
        self.minsize(1020, 640)

        # 🎨 Balanced, Harmonious Obsidian & Slate Palette
        self.C_BG_ROOT     = "#0A0C13"  # Deep Obsidian night
        self.C_CARD_BG     = "#121520"  # Cohesive slate card
        self.C_CARD_HEADER = "#161A28"  # Subtle elevated header
        self.C_CARD_BORDER = "#1E2436"  # 1px hairline card stroke
        self.C_CHAT_BG     = "#080A0F"  # High contrast chat canvas
        self.C_LOG_BG      = "#07090D"  # Jet black developer terminal
        
        # Typography Colors
        self.C_TEXT_MAIN   = "#F1F5F9"  # Crisp clean white
        self.C_TEXT_MUTED  = "#94A3B8"  # Balanced slate secondary
        self.C_TEXT_DIM    = "#64748B"  # Dim subtle text
        
        # Semantic Brand Accents
        self.C_INDIGO      = "#6366F1"  # Primary electric indigo
        self.C_INDIGO_HOV  = "#4F46E5"
        self.C_INDIGO_ACT  = "#4338CA"

        self.C_EMERALD     = "#059669"  # Pinecone & Success
        self.C_EMERALD_HOV = "#10B981"
        self.C_EMERALD_ACT = "#047857"

        self.C_SLATE_BTN   = "#1B2030"  # Secondary tool buttons
        self.C_SLATE_HOV   = "#283049"
        self.C_SLATE_ACT   = "#141824"
        self.C_SLATE_BRD   = "#2C344D"

        self.C_AMBER       = "#D97706"  # Pause & Warning
        self.C_AMBER_HOV   = "#F59E0B"
        
        self.C_ROSE        = "#DC2626"  # Stop & Error
        self.C_ROSE_HOV    = "#EF4444"

        self.C_CYAN        = "#0891B2"  # System telemetry
        self.C_CYAN_HOV    = "#06B6D4"

        self.configure(bg=self.C_BG_ROOT)
        self._setup_styles()

        self.session = ChatSession()
        self.log_queue = queue.Queue()
        self.is_processing = False
        self.chat_mode_val = "general"

        # Redirect stdout and stderr
        sys.stdout = LogRedirector(self.log_queue, sys.__stdout__)
        sys.stderr = LogRedirector(self.log_queue, sys.__stderr__)

        # Build Layout
        self._build_ui()

        # Register task controller callback
        task_controller.register_callback(self._on_task_progress)

        # Start log queue polling loop
        self.after(100, self._poll_log_queue)

        print("✨ [Aayie OS] Ultra-Modern Obsidian Dashboard loaded successfully!")
        self._append_chat("Aayie", "Namaste! Main aapka AI Personal Assistant Aayie hoon. 🤖✨\n\n"
                                  "Main Web Search, Weather, Google Sheets, State CSV Creation, aur Pinecone Vector RAG kar sakta hoon.\n\n"
                                  "💬 Niche diye gaye quick chips click karein ya direct query type karein!")

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=self.C_BG_ROOT, foreground=self.C_TEXT_MAIN, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.C_BG_ROOT)
        
        # Smooth modern progressbar style
        style.configure("Smooth.Horizontal.TProgressbar", 
                        thickness=12, 
                        troughcolor="#181C2B", 
                        background=self.C_INDIGO,
                        bordercolor="#121520",
                        lightcolor=self.C_INDIGO,
                        darkcolor=self.C_INDIGO)

    def _build_ui(self):
        # ═════════════════════════════════════════════════════════
        # 1. TOP NAVBAR / HEADER
        # ═════════════════════════════════════════════════════════
        header_bar = tk.Frame(self, bg=self.C_CARD_BG, height=58, highlightbackground=self.C_CARD_BORDER, highlightthickness=1)
        header_bar.pack(fill="x", side="top", padx=14, pady=(12, 8))

        # Brand Logo & Subtitle (Left)
        brand_frame = tk.Frame(header_bar, bg=self.C_CARD_BG)
        brand_frame.pack(side="left", padx=16, pady=12)

        logo_lbl = tk.Label(
            brand_frame, 
            text="✦ AAYIE AI", 
            font=("Segoe UI", 13, "bold"), 
            bg=self.C_CARD_BG, 
            fg=self.C_INDIGO
        )
        logo_lbl.pack(side="left")

        sub_lbl = tk.Label(
            brand_frame, 
            text="  •  Autonomous Agent & Tour RAG v2.5", 
            font=("Segoe UI", 9), 
            bg=self.C_CARD_BG, 
            fg=self.C_TEXT_MUTED
        )
        sub_lbl.pack(side="left")

        # Actions & Status Pill (Right)
        actions_frame = tk.Frame(header_bar, bg=self.C_CARD_BG)
        actions_frame.pack(side="right", padx=14, pady=10)

        # Status Pill Badge
        self.status_badge = tk.Label(
            actions_frame,
            text="● SYSTEM ONLINE",
            font=("Segoe UI", 8, "bold"),
            bg="#064E3B",
            fg="#6EE7B7",
            padx=12,
            pady=4,
            relief="flat"
        )
        self.status_badge.pack(side="right", padx=(10, 0))

        # Smooth Action Pill Buttons
        self.btn_push_pinecone = SmoothButton(
            actions_frame,
            text="🌲 Sync Pinecone",
            bg_color=self.C_EMERALD,
            hover_color=self.C_EMERALD_HOV,
            active_color=self.C_EMERALD_ACT,
            parent_bg=self.C_CARD_BG,
            radius=8,
            height=28,
            command=self._on_push_pinecone_click
        )
        self.btn_push_pinecone.pack(side="right", padx=4)

        self.btn_create_csv = SmoothButton(
            actions_frame,
            text="📄 Create CSV",
            bg_color=self.C_SLATE_BTN,
            hover_color=self.C_SLATE_HOV,
            active_color=self.C_SLATE_ACT,
            text_color="#CBD5E1",
            border_color=self.C_SLATE_BRD,
            parent_bg=self.C_CARD_BG,
            radius=8,
            height=28,
            command=self._on_create_csv_click
        )
        self.btn_create_csv.pack(side="right", padx=4)

        self.btn_repair_csv = SmoothButton(
            actions_frame,
            text="🛠 Repair CSV",
            bg_color=self.C_SLATE_BTN,
            hover_color=self.C_SLATE_HOV,
            active_color=self.C_SLATE_ACT,
            text_color="#CBD5E1",
            border_color=self.C_SLATE_BRD,
            parent_bg=self.C_CARD_BG,
            radius=8,
            height=28,
            command=self._on_repair_csv_click
        )
        self.btn_repair_csv.pack(side="right", padx=4)

        # ═════════════════════════════════════════════════════════
        # 2. MAIN BODY (LEFT CHAT + RIGHT CONSOLE)
        # ═════════════════════════════════════════════════════════
        body_container = tk.Frame(self, bg=self.C_BG_ROOT)
        body_container.pack(fill="both", expand=True, padx=14, pady=4)

        # ─────────────────────────────────────────────────────────
        # LEFT CARD: CONVERSATION & INTELLIGENCE
        # ─────────────────────────────────────────────────────────
        left_card = tk.Frame(body_container, bg=self.C_CARD_BG, highlightbackground=self.C_CARD_BORDER, highlightthickness=1)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 7))

        # Card Header: Title & Segmented Mode Switcher
        left_header = tk.Frame(left_card, bg=self.C_CARD_HEADER, height=44)
        left_header.pack(fill="x")

        lbl_chat_title = tk.Label(
            left_header, 
            text="💬 Conversational Intelligence", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.C_CARD_HEADER, 
            fg=self.C_TEXT_MAIN
        )
        lbl_chat_title.pack(side="left", padx=14, pady=10)

        # Segmented Mode Switcher
        mode_options = [
            ("general", "🤖 Aayie General", self.C_INDIGO, self.C_INDIGO_HOV),
            ("tour_rag", "🌲 Tour RAG Engine", self.C_EMERALD, self.C_EMERALD_HOV)
        ]
        self.mode_switcher = SmoothSegmentedSwitcher(
            left_header,
            options=mode_options,
            current_val=self.chat_mode_val,
            on_change=self._on_segmented_mode_change,
            bg=self.C_CARD_HEADER
        )
        self.mode_switcher.pack(side="right", padx=10, pady=8)

        # Chat Canvas (ScrolledText)
        self.chat_display = ScrolledText(
            left_card, 
            wrap="word", 
            bg=self.C_CHAT_BG, 
            fg=self.C_TEXT_MAIN, 
            insertbackground="#FFFFFF",
            font=("Segoe UI", 10),
            padx=16,
            pady=16,
            state="disabled",
            relief="flat",
            highlightthickness=0
        )
        self.chat_display.pack(fill="both", expand=True, padx=12, pady=(10, 6))

        # Chat Bubble Formatting Tags
        self.chat_display.tag_configure("user_hdr", foreground="#38BDF8", font=("Segoe UI", 9, "bold"))
        self.chat_display.tag_configure("user_txt", foreground="#E0F2FE", font=("Segoe UI", 10))
        
        self.chat_display.tag_configure("ai_hdr", foreground=self.C_INDIGO, font=("Segoe UI", 9, "bold"))
        self.chat_display.tag_configure("ai_txt", foreground="#F8FAFC", font=("Segoe UI", 10))
        
        self.chat_display.tag_configure("rag_hdr", foreground="#34D399", font=("Segoe UI", 9, "bold"))
        self.chat_display.tag_configure("rag_txt", foreground="#ECFDF5", font=("Segoe UI", 10))

        self.chat_display.tag_configure("sys_hdr", foreground="#FBBF24", font=("Segoe UI", 9, "bold"))
        self.chat_display.tag_configure("sys_txt", foreground="#FEF3C7", font=("Segoe UI", 9, "italic"))

        self.chat_display.tag_configure("divider", foreground="#23283B", font=("Segoe UI", 8))

        # Quick Suggestion Chips Bar
        chips_frame = tk.Frame(left_card, bg=self.C_CARD_BG)
        chips_frame.pack(fill="x", padx=14, pady=(2, 6))

        tk.Label(chips_frame, text="Quick Prompt:", font=("Segoe UI", 8), bg=self.C_CARD_BG, fg=self.C_TEXT_DIM).pack(side="left", padx=(0, 6))

        chips = [
            ("🌲 Bihar Places RAG", "Bihar ke top tourist places aur unke ticket details batao"),
            ("📄 Create Bihar CSV", "Bihar ka csv file create karo"),
            ("🛠 Repair Bihar CSV", "Bihar places csv repair karo missing clean"),
            ("⛅ Patna Weather", "Patna ka weather kaisa hai?"),
            ("🧹 Clear Chat", "clear")
        ]
        for chip_label, chip_query in chips:
            c_btn = SmoothButton(
                chips_frame,
                text=chip_label,
                bg_color="#181C2B",
                hover_color="#242B42",
                active_color="#141825",
                text_color="#94A3B8",
                border_color="#272F47",
                radius=6,
                height=24,
                parent_bg=self.C_CARD_BG,
                font=("Segoe UI", 8),
                padx=8,
                command=lambda q=chip_query: self._on_chip_click(q)
            )
            c_btn.pack(side="left", padx=2)

        # Input Box Frame with Smooth Accent Border
        input_border_frame = tk.Frame(left_card, bg="#272E44", padx=1, pady=1)
        input_border_frame.pack(fill="x", padx=14, pady=(0, 12))

        input_inner = tk.Frame(input_border_frame, bg="#10131E")
        input_inner.pack(fill="x")

        self.entry_input = tk.Entry(
            input_inner, 
            bg="#10131E", 
            fg="#FFFFFF", 
            insertbackground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=0
        )
        self.entry_input.pack(side="left", fill="x", expand=True, padx=12, pady=7)
        self.entry_input.bind("<Return>", lambda event: self._send_message())

        btn_send = SmoothButton(
            input_inner, 
            text="✦ Send 📤", 
            bg_color=self.C_INDIGO, 
            hover_color=self.C_INDIGO_HOV,
            active_color=self.C_INDIGO_ACT,
            radius=7,
            height=26,
            parent_bg="#10131E",
            command=self._send_message
        )
        btn_send.pack(side="right", padx=5, pady=4)

        # ─────────────────────────────────────────────────────────
        # RIGHT CARD: MAC-STYLE DEVELOPER CONSOLE & LOGS
        # ─────────────────────────────────────────────────────────
        right_card = tk.Frame(body_container, bg=self.C_CARD_BG, highlightbackground=self.C_CARD_BORDER, highlightthickness=1)
        right_card.pack(side="right", fill="both", expand=True, padx=(7, 0))

        # Mac-Style Console Header
        console_hdr = tk.Frame(right_card, bg=self.C_CARD_HEADER, height=44)
        console_hdr.pack(fill="x")

        # Traffic light dots
        dots_frame = tk.Frame(console_hdr, bg=self.C_CARD_HEADER)
        dots_frame.pack(side="left", padx=12, pady=10)

        tk.Label(dots_frame, text="●", font=("Segoe UI", 10), bg=self.C_CARD_HEADER, fg="#EF4444").pack(side="left", padx=2)
        tk.Label(dots_frame, text="●", font=("Segoe UI", 10), bg=self.C_CARD_HEADER, fg="#F59E0B").pack(side="left", padx=2)
        tk.Label(dots_frame, text="●", font=("Segoe UI", 10), bg=self.C_CARD_HEADER, fg="#10B981").pack(side="left", padx=2)

        lbl_console_title = tk.Label(
            console_hdr,
            text="aayie-console:~$ live-telemetry",
            font=("Consolas", 9, "bold"),
            bg=self.C_CARD_HEADER,
            fg=self.C_TEXT_MUTED
        )
        lbl_console_title.pack(side="left", padx=8)

        btn_clear_console = SmoothButton(
            console_hdr,
            text="🧹 Clear",
            bg_color="#1E2436",
            hover_color="#2D3650",
            active_color="#161B29",
            text_color="#94A3B8",
            border_color="#2C3550",
            radius=6,
            height=22,
            parent_bg=self.C_CARD_HEADER,
            font=("Segoe UI", 8),
            padx=8,
            command=self._clear_logs
        )
        btn_clear_console.pack(side="right", padx=10, pady=8)

        # Log Display Canvas
        self.log_display = ScrolledText(
            right_card, 
            wrap="word", 
            bg=self.C_LOG_BG, 
            fg="#94A3B8", 
            insertbackground="#FFFFFF",
            font=("Consolas", 9),
            padx=12,
            pady=12,
            state="disabled",
            relief="flat",
            highlightthickness=0
        )
        self.log_display.pack(fill="both", expand=True, padx=12, pady=(10, 12))

        # Syntax tags for Console Logs
        self.log_display.tag_configure("log_success", foreground="#34D399")
        self.log_display.tag_configure("log_error", foreground="#F87171")
        self.log_display.tag_configure("log_warn", foreground="#FBBF24")
        self.log_display.tag_configure("log_info", foreground="#67E8F9")
        self.log_display.tag_configure("log_purple", foreground="#A78BFA")
        self.log_display.tag_configure("log_pinecone", foreground="#6EE7B7")

        # ═════════════════════════════════════════════════════════
        # 3. BOTTOM PANEL: LIVE TASK CONTROLLER & PROGRESS
        # ═════════════════════════════════════════════════════════
        bottom_card = tk.Frame(self, bg=self.C_CARD_BG, highlightbackground=self.C_CARD_BORDER, highlightthickness=1)
        bottom_card.pack(fill="x", side="bottom", padx=14, pady=(4, 12))

        ctrl_box = tk.Frame(bottom_card, bg=self.C_CARD_BG)
        ctrl_box.pack(fill="x", padx=14, pady=8)

        # Smooth Control Buttons
        self.btn_pause = SmoothButton(
            ctrl_box, 
            text="⏸ PAUSE", 
            bg_color=self.C_AMBER, 
            hover_color=self.C_AMBER_HOV,
            active_color="#B45309",
            radius=8,
            height=28,
            parent_bg=self.C_CARD_BG,
            command=self._on_pause_click
        )
        self.btn_pause.pack(side="left", padx=(0, 6))

        self.btn_resume = SmoothButton(
            ctrl_box, 
            text="▶ RESUME", 
            bg_color=self.C_EMERALD, 
            hover_color=self.C_EMERALD_HOV,
            active_color=self.C_EMERALD_ACT,
            radius=8,
            height=28,
            parent_bg=self.C_CARD_BG,
            command=self._on_resume_click
        )
        self.btn_resume.pack(side="left", padx=4)

        self.btn_stop = SmoothButton(
            ctrl_box, 
            text="⏹ STOP", 
            bg_color=self.C_ROSE, 
            hover_color=self.C_ROSE_HOV,
            active_color="#B91C1C",
            radius=8,
            height=28,
            parent_bg=self.C_CARD_BG,
            command=self._on_stop_click
        )
        self.btn_stop.pack(side="left", padx=4)

        # Live Status Label
        self.lbl_task_status = tk.Label(
            ctrl_box, 
            text="Status: Ready | Task: Idle", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.C_CARD_BG, 
            fg="#38BDF8"
        )
        self.lbl_task_status.pack(side="left", padx=16)

        # Percentage indicator
        self.lbl_pct = tk.Label(
            ctrl_box,
            text="0%",
            font=("Segoe UI", 9, "bold"),
            bg=self.C_CARD_BG,
            fg=self.C_TEXT_MUTED
        )
        self.lbl_pct.pack(side="right", padx=(8, 0))

        # Smooth Progressbar
        self.progress_bar = ttk.Progressbar(
            ctrl_box, 
            orient="horizontal", 
            mode="determinate", 
            style="Smooth.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(12, 0))

    # ─────────────────────────────────────────────
    # UI Actions & Logging
    # ─────────────────────────────────────────────

    def _append_chat(self, sender: str, text: str):
        self.chat_display.config(state="normal")
        div_line = "────────────────────────────────────────────────────────────\n"

        if sender == "User":
            self.chat_display.insert("end", f"\n🧑 AAP (USER)\n", "user_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n", "user_txt")
            self.chat_display.insert("end", div_line, "divider")
        elif "TourKaro" in sender or "RAG" in sender:
            self.chat_display.insert("end", f"\n🌲 TOUR RAG ENGINE (PINECONE VERIFIED)\n", "rag_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n", "rag_txt")
            self.chat_display.insert("end", div_line, "divider")
        elif sender == "Aayie":
            self.chat_display.insert("end", f"\n🤖 AAYIE AI ASSISTANT\n", "ai_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n", "ai_txt")
            self.chat_display.insert("end", div_line, "divider")
        else:
            self.chat_display.insert("end", f"\n⚡ SYSTEM NOTICE ({sender})\n", "sys_hdr")
            self.chat_display.insert("end", f"{text.strip()}\n", "sys_txt")
            self.chat_display.insert("end", div_line, "divider")

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
        
        if any(w in msg for w in ["✅", "Successfully", "Completed", "Done"]):
            tag = "log_success"
        elif any(w in msg for w in ["❌", "Error", "Failed", "Exception"]):
            tag = "log_error"
        elif any(w in msg for w in ["⚠️", "⚠", "PAUSED", "Waiting"]):
            tag = "log_warn"
        elif any(w in msg for w in ["🌲", "Pinecone", "mxbai", "Vector", "Embed"]):
            tag = "log_pinecone"
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

    def _on_chip_click(self, query: str):
        if query == "clear":
            self.session.clear()
            self._append_chat("System", "Chat history saaf ho gayi.")
            return
        self.entry_input.delete(0, "end")
        self.entry_input.insert(0, query)
        self._send_message()

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
        self.status_badge.config(text="● PROCESSING...", bg="#78350F", fg="#FEF08A")
        self.lbl_task_status.config(text="Status: Thinking / Executing... ⏳", fg="#F59E0B")

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
            self.after(0, self.status_badge.config, {"text": "● SYSTEM ONLINE", "bg": "#064E3B", "fg": "#6EE7B7"})
            self.after(0, self.lbl_task_status.config, {"text": "Status: Ready | Task: Idle", "fg": "#38BDF8"})

    async def _process_query(self, user_input: str):
        # ── Tour RAG Testing Mode ──────────────────────────
        if self.chat_mode_val == "tour_rag":
            print(f"\n🌲 [Tour RAG Mode] Querying Pinecone Vector Index for: '{user_input}'...")
            self.session.add_user(user_input)
            from agent.services.tour_rag_service import query_tour_rag, format_rag_response_for_chat
            rag_res = query_tour_rag(user_input)
            formatted_ans = format_rag_response_for_chat(rag_res)
            self.session.add_assistant(formatted_ans)
            self.after(0, self._append_chat, "TourKaro AI (Pinecone RAG)", formatted_ans)
            return

        history_str = ""
        for msg in self.session.get_history()[-6:]:
            role = "Aap" if msg["role"] == "user" else "Aayie"
            history_str += f"{role}: {msg['content']}\n"

        print(f"\n🔍 [GUI] Intent classify ho raha hai...")
        lower_input = user_input.lower()
        if "json" in lower_input and ("update" in lower_input or "sync" in lower_input or "karo" in lower_input or "check" in lower_input or "file" in lower_input):
            intent = "SYNC_JSON"
        elif "pinecone" in lower_input and ("push" in lower_input or "sync" in lower_input or "embed" in lower_input or "daalo" in lower_input or "upload" in lower_input):
            intent = "PUSH_PINECONE"
        elif "csv" in lower_input and ("repair" in lower_input or "fix" in lower_input or "theek" in lower_input or "missing" in lower_input or "clean" in lower_input):
            intent = "REPAIR_CSV"
        elif "csv" in lower_input and ("create" in lower_input or "banao" in lower_input or "generate" in lower_input or "file" in lower_input or "karo" in lower_input or "save" in lower_input):
            intent = "CREATE_CSV"
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

        elif intent == "PUSH_PINECONE":
            print("🌲 State Places Pinecone Sync pipeline chal raha hai...")
            state, _ = extract_enrich_params(user_input)
            if not state:
                state = "Bihar"

            from agent.tools.pinecone_sync_tool import push_state_csv_to_pinecone
            res_msg = push_state_csv_to_pinecone(state_name=state)
            self.session.add_assistant(str(res_msg))
            self.after(0, self._append_chat, "Aayie", f"Pinecone Sync Result:\n{res_msg}")

        elif intent == "REPAIR_CSV":
            print("🛠 State Places CSV Repair pipeline chal raha hai...")
            state, city = extract_enrich_params(user_input)
            if not state:
                state = "Bihar"

            from agent.tools.repair_csv_tool import repair_state_csv
            res_msg = repair_state_csv(state_name=state, city_filter=city)
            self.session.add_assistant(str(res_msg))
            self.after(0, self._append_chat, "Aayie", f"CSV Repair Result:\n{res_msg}")

        elif intent == "CREATE_CSV":
            print("📄 State Places CSV Creation pipeline chal raha hai...")
            state, city = extract_enrich_params(user_input)
            if not state:
                msg = "Could not understand state name for CSV creation. Please specify state (e.g. 'Bihar ka csv file create karo')."
                self.after(0, self._append_chat, "Aayie", msg)
                return

            from agent.tools.create_csv_tool import create_state_csv
            res_msg = create_state_csv(state_name=state, city_filter=city)
            self.session.add_assistant(str(res_msg))
            self.after(0, self._append_chat, "Aayie", f"CSV Creation Result:\n{res_msg}")

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
        self.status_badge.config(text="● PAUSED", bg="#78350F", fg="#FEF08A")
        self.lbl_task_status.config(text="Status: PAUSING after current item... ⏸️", fg="#F59E0B")

    def _on_resume_click(self):
        task_controller.resume()
        self.status_badge.config(text="● PROCESSING", bg="#78350F", fg="#FEF08A")
        self.lbl_task_status.config(text="Status: RESUMED & RUNNING ▶️", fg="#10B981")

    def _on_stop_click(self):
        task_controller.stop()
        self.status_badge.config(text="● STOPPED", bg="#7F1D1D", fg="#FCA5A5")
        self.lbl_task_status.config(text="Status: STOPPED ⏹️", fg="#EF4444")
        self.progress_bar["value"] = 0
        self.lbl_pct.config(text="0%")

    def _on_segmented_mode_change(self, mode: str):
        self.chat_mode_val = mode
        if mode == "tour_rag":
            self._append_chat("System", "🌲 Switched to [Tour RAG Vector Engine] Mode!\n"
                                        "Queries will now be searched against Pinecone Index ('sonukumar') "
                                        "embedded via 'mxbai-embed-large'. Test questions: 'Golghar ka ticket kitna hai?' or 'Bodh Gaya me monastery timing kya hai?'.")
        else:
            self._append_chat("System", "🤖 Switched to [Aayie General Assistant] Mode!\n"
                                        "General conversation, web search, weather, sheets, and system tools are active.")

    def _on_push_pinecone_click(self):
        if self.is_processing:
            return
        state_input = simpledialog.askstring(
            "Push CSV to Pinecone",
            "Enter State Name to sync with Pinecone (e.g. Bihar, Uttar Pradesh):",
            parent=self
        )
        if state_input and state_input.strip():
            query = f"{state_input.strip()} places csv ko Pinecone me push karo"
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, query)
            self._send_message()

    def _on_create_csv_click(self):
        if self.is_processing:
            return
        state_input = simpledialog.askstring(
            "Create State CSV",
            "Enter State Name (e.g. Bihar, Uttar Pradesh, Goa):",
            parent=self
        )
        if state_input and state_input.strip():
            query = f"{state_input.strip()} ka csv file create karo"
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, query)
            self._send_message()

    def _on_repair_csv_click(self):
        if self.is_processing:
            return
        state_input = simpledialog.askstring(
            "Repair State CSV",
            "Enter State Name to repair missing fields (e.g. Bihar):",
            parent=self
        )
        if state_input and state_input.strip():
            query = f"{state_input.strip()} places csv repair karo missing clean"
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, query)
            self._send_message()

    def _on_task_progress(self, task_name: str, idx: int, total: int, item_name: str, status: str):
        def _update():
            if total > 0:
                pct = int((idx / total) * 100)
                self.progress_bar["value"] = pct
                self.lbl_pct.config(text=f"{pct}%")
            else:
                pct = 0
                self.lbl_pct.config(text="0%")

            if status == "PAUSED":
                self.status_badge.config(text="● PAUSED", bg="#78350F", fg="#FEF08A")
                self.lbl_task_status.config(text=f"⏸️ PAUSED at [{idx}/{total}] '{item_name}'", fg="#F59E0B")
            elif status == "PAUSED_REQUESTED":
                self.status_badge.config(text="● PAUSING...", bg="#78350F", fg="#FEF08A")
                self.lbl_task_status.config(text=f"⏸️ PAUSING after '{item_name}' finishes...", fg="#F59E0B")
            elif status == "STOPPED":
                self.status_badge.config(text="● STOPPED", bg="#7F1D1D", fg="#FCA5A5")
                self.lbl_task_status.config(text=f"⏹️ STOPPED at [{idx}/{total}]", fg="#EF4444")
            elif status == "RUNNING":
                self.status_badge.config(text="● PROCESSING", bg="#064E3B", fg="#6EE7B7")
                self.lbl_task_status.config(text=f"▶️ [{idx}/{total}] ({pct}%): {item_name}", fg="#10B981")
            elif status == "STARTED":
                self.status_badge.config(text="● STARTED", bg="#1E3A8A", fg="#93C5FD")
                self.lbl_task_status.config(text=f"🚀 Started {task_name} (0/{total})", fg=self.C_INDIGO)

        self.after(0, _update)


if __name__ == "__main__":
    app = AayieGUI()
    app.mainloop()
