"""
agent/router.py — User input ko classify karta hai specific tool ke hisaab se.

Intents:
  CHAT           : Greetings, casual conversation, general knowledge
  WEB_SEARCH     : Questions needing internet research
  WEATHER        : Weather queries
  GOOGLE_SHEETS  : Read/write Google Sheets
  SYSTEM_ACTION  : File operations, open apps, folder management
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

_model = OllamaLLM(model="llama3.2", keep_alive=-1)

_router_template = """You are an intent classifier for an AI personal assistant.

Classify the user's message into EXACTLY ONE category from below:

  CHAT           - Greetings, small talk, casual questions, general knowledge you already know
                   Examples: "hello", "how are you", "what is 2+2", "can you help me?", 
                             "hi", "what can you do?", "tell me a joke"

  WEB_SEARCH     - Questions needing current/specific information from the internet
                   Examples: "tell me about Sikkim", "latest news on AI", "best hotels in Goa",
                             "who won IPL 2024", "explain quantum computing"

  WEATHER        - Any query about weather, temperature, forecast, rain, climate for a location
                   Examples: "weather in Delhi", "will it rain tomorrow in Mumbai", "temperature today"

  GOOGLE_SHEETS  - Reading, writing, updating, appending data to a Google Sheet (general operations)
                   Examples: "fill my spreadsheet with...", "add row to google sheet",
                             "read data from my sheet", "update column in spreadsheet"

  ENRICH_SHEET   - specifically for fetching tourist place data (from JSON, Wikipedia, Google) 
                   and updating it into state-wise tabs in the Google Sheet.
                   Examples: "Bihar Kaimur ke places sheet mein daalo",
                             "Update Goa sheet with Wikipedia data",
                             "Rajasthan ke places sheet mein fill karo"

  REPAIR_SHEET   - specifically for scanning an existing state sheet to fix empty or "negative" LLM 
                   responses by performing a Google Search. 
                   Examples: "Bihar ke places check karo aur sheet ko repair karo",
                             "filter bihar sheet and fix missing data",
                             "repair sheet for Goa"

  SYNC_JSON      - specifically for updating, checking, or syncing tourist places JSON files 
                   between source database and local destination Places_db (filling descriptions, 
                   creating missing state JSON files, etc.).
                   Examples: "json file update karo", "sync json files",
                             "update places json from tourkaro", "json sync karo"

  SYSTEM_ACTION  - Computer control: open apps, create/read/write/delete/move local files,
                   list folders, run scripts, manage local system
                   Examples: "open VS Code", "create a folder called reports",
                             "read my config.json", "show files in Downloads",
                             "write to notes.txt", "open notepad", "open chrome"

Rules:
  - Reply with ONLY the category name. No explanation, no punctuation, no other text.
  - "can you help me", "do my work", "what can you do" = CHAT (these are conversational)
  - Only use SYSTEM_ACTION for explicit computer/file/app tasks
  - When unsure between CHAT and WEB_SEARCH, use WEB_SEARCH
  - Opening any application (VS Code, Chrome, Notepad, etc.) = SYSTEM_ACTION

User Message: {query}

Intent:"""

_router_prompt = ChatPromptTemplate.from_template(_router_template)
_router_chain  = _router_prompt | _model

VALID_INTENTS = {"CHAT", "WEB_SEARCH", "WEATHER", "GOOGLE_SHEETS", "SYSTEM_ACTION", "ENRICH_SHEET", "REPAIR_SHEET", "SYNC_JSON"}



def classify_intent(query: str) -> str:
    """
    User ke query ka intent classify karo.
    Returns one of: CHAT, WEB_SEARCH, WEATHER, GOOGLE_SHEETS, SYSTEM_ACTION
    """
    raw = _router_chain.invoke({"query": query})
    intent = raw.strip().upper().split()[0]  # Only first word to avoid trailing text

    for valid in VALID_INTENTS:
        if valid in intent:
            return valid

    print(f"  ⚠ Router unknown intent '{raw}', defaulting to CHAT")
    return "CHAT"
