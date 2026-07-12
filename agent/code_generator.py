"""
agent/code_generator.py — User ke task ke liye Python code generate karta hai.

Uses llama3.2 (already in VRAM) to write safe, executable Python code.
"""

import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

_model = OllamaLLM(model="llama3.2", keep_alive=-1)

_codegen_template = """You are a Python code-writing assistant running on a Windows 10/11 machine.

The user wants you to perform a task on their computer. Write Python code that accomplishes this.

Available libraries (already installed, import what you need):
  os, sys, subprocess, pathlib, shutil, glob, json, csv, re, datetime, time, random
  pandas, openpyxl, xlrd, requests

Working directory: {cwd}

STRICT Rules:
  1. Write ONLY executable Python code inside a ```python ... ``` code block.
  2. ALL imports MUST be at the very top of the code. NEVER use a name without importing it.
  3. Use `from pathlib import Path` for ALL file operations.
  4. Wrap the main logic in a try/except block.
  5. Always print a short English message at the end describing what was done.
  6. ALL comments and print statements MUST be in ENGLISH ONLY. No Hindi, no other language.
  7. Do NOT install packages using pip.
  8. Do NOT delete system files or use dangerous shell commands.
  9. NEVER hardcode full application paths like "C:/Program Files/...". 
     Instead, use the application's command that is already on PATH:
       - VS Code  → subprocess.Popen(["code", "."], shell=True)
       - Notepad  → subprocess.Popen(["notepad"], shell=True)
       - Chrome   → subprocess.Popen(["start", "chrome"], shell=True)
       - Any app  → subprocess.Popen(["start", app_name], shell=True)
  11. For shell commands like 'start', 'dir', use shell=True.
  12. If the user asks to "open chrome and search something" or "search Google", use the `webbrowser` module:
      Example: import webbrowser; webbrowser.open("https://www.google.com/search?q=your+query")

User Task: {task}

Python Code:"""

_codegen_prompt = ChatPromptTemplate.from_template(_codegen_template)
_codegen_chain  = _codegen_prompt | _model


def generate_code(task: str, cwd: str) -> str:
    """
    User ke task ke liye Python code generate karo.
    Returns: clean Python code string (without markdown fences)
    """
    print("  ✍ Code generate ho raha hai (llama3.2)...")
    raw_response = _codegen_chain.invoke({"task": task, "cwd": cwd})

    # Extract code block from markdown fences
    code_match = re.search(r"```python\s*(.*?)```", raw_response, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()

    # If no fences, try to return everything after the last blank line
    code_match_plain = re.search(r"```\s*(.*?)```", raw_response, re.DOTALL)
    if code_match_plain:
        return code_match_plain.group(1).strip()

    # Last resort: return as-is
    return raw_response.strip()
