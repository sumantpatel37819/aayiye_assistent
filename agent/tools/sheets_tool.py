"""
agent/tools/sheets_tool.py — Google Sheets read/write tool.
Uses GOOGLE_SHEETS_ID and GOOGLE_CREDENTIALS_JSON from .env file.

Setup:
  1. Google Cloud Console me ek Service Account banao
  2. Google Sheets API enable karo
  3. credentials.json file download karo
  4. .env me GOOGLE_CREDENTIALS_JSON path aur GOOGLE_SHEETS_ID daalo
  5. Apni sheet me us Service Account ko "Editor" access do
"""

import os
import json
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM


# ─────────────────────────────────────────────
# Load .env variables
# ─────────────────────────────────────────────

def _load_env():
    env_path = Path(__file__).parent.parent.parent / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _get_sheet_service():
    """Google Sheets API service banao."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API libraries nahi hain. Install karo:\n"
            "  pip install google-auth google-auth-httplib2 google-api-python-client"
        )
    
    env = _load_env()
    creds_val = env.get("GOOGLE_CREDENTIALS_JSON", "credentials.json")
    
    # Resolve absolute path based on project root
    root_dir = Path(__file__).parent.parent.parent
    creds_path = Path(creds_val)
    if not creds_path.is_absolute():
        creds_path = root_dir / creds_val
    
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials file nahi mila: '{creds_path}'\n"
            f".env me GOOGLE_CREDENTIALS_JSON=path/to/credentials.json set karo."
        )
    
    creds = Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)


# ─────────────────────────────────────────────
# LLM: Parse user instruction into structured action
# ─────────────────────────────────────────────

_model = OllamaLLM(model="llama3.2", keep_alive=-1)

_parse_template = """You are a Google Sheets assistant. Parse the user's instruction into a structured JSON action.

Actions available:
  - read: Read data from sheet
  - write: Write data to a specific cell or range
  - append: Append a new row to the sheet
  - clear: Clear a range

User Instruction: {instruction}

Current sheet ID: {sheet_id}

Respond with ONLY valid JSON (no explanation):
{{
  "action": "read" | "write" | "append" | "clear",
  "sheet_name": "Sheet1",
  "range": "A1:D10",
  "values": [[row1col1, row1col2], [row2col1]] (for write/append, else null)
}}"""

_parse_prompt = ChatPromptTemplate.from_template(_parse_template)
_parse_chain  = _parse_prompt | _model


def get_existing_places_from_sheet(state_name: str) -> dict:
    """
    Fetches existing rows for a given state from Google Sheets.
    Returns a dict mapping 'famous_place_title' (or name) to its row index (1-based) and data.
    Format: {"Mehrangarh Fort": {"row_index": 2, "data": ["Id", "district", ...]}}
    """
    try:
        service = _get_sheet_service()
        env = _load_env()
        spreadsheet_id = env.get("GOOGLE_SHEETS_ID")
        if not spreadsheet_id:
            return {}

        # Check if sheet exists (case-insensitive)
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        sheet_names = [sheet['properties']['title'] for sheet in sheets]
        
        target_tab = None
        for sname in sheet_names:
            if sname.strip().lower() == state_name.strip().lower():
                target_tab = sname
                break

        if not target_tab:
            print(f"  ⚠ Tab '{state_name}' not found in Google Sheet. Available tabs: {sheet_names}")
            return {}

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{target_tab}!A:Q"
        ).execute()
        
        rows = result.get("values", [])
        if not rows or len(rows) < 2:
            return {}
            
        existing_places = {}
        # Assuming row[3] is famous_place_name and row[4] is famous_place_title based on CSV_COLUMNS
        for idx, row in enumerate(rows):
            if idx == 0: continue # Skip header
            
            # Pad the row to 17 columns just in case some trailing columns are empty
            padded_row = row + [""] * (17 - len(row))
            
            place_name = padded_row[3].strip().lower()
            place_title = padded_row[4].strip().lower()
            
            # Store using both name and title to ensure robust matching
            row_info = {"row_index": idx + 1, "data": padded_row}
            if place_name: existing_places[place_name] = row_info
            if place_title: existing_places[place_title] = row_info
            
        return existing_places

    except Exception as e:
        print(f"    ⚠ Error reading existing sheet data: {e}")
        return {}


def update_enriched_row_in_sheet(state_name: str, row_index: int, row_data: list) -> str:
    """
    Updates a specific row in the Google Sheet.
    """
    try:
        service = _get_sheet_service()
        env = _load_env()
        spreadsheet_id = env.get("GOOGLE_SHEETS_ID")
        
        body = {"values": [row_data]}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{state_name}!A{row_index}:Q{row_index}",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return f"Successfully updated row {row_index} in the '{state_name}' tab."
    except Exception as e:
        return f"Error updating Google Sheets: {e}"


def write_enriched_rows_to_sheet(state_name: str, rows: list[dict]) -> str:
    """
    Creates a tab for the state (if it doesn't exist) and appends rows.
    Rows are lists of dictionaries mapping to the CSV structure.
    """
    try:
        service = _get_sheet_service()
        env = _load_env()
        spreadsheet_id = env.get("GOOGLE_SHEETS_ID")
        if not spreadsheet_id:
            return "Error: GOOGLE_SHEETS_ID not found in .env"

        # Check if sheet exists, if not, create it
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        sheet_names = [sheet['properties']['title'] for sheet in sheets]
        
        # Define CSV Columns
        csv_columns = [
            "Id", "district", "Place", "famous_place_name", "famous_place_title",
            "Description", "Recognition", "culture", "Location",
            "Address_from_Capital", "means_of_transport", "Famous_Dish",
            "History", "reference", "Temple_reference", "Image URL from wikipedia"
        ]

        if state_name not in sheet_names:
            print(f"    📄 Creating new tab for {state_name}...")
            # Create the sheet
            batch_update_spreadsheet_request_body = {
                'requests': [
                    {
                        'addSheet': {
                            'properties': {
                                'title': state_name,
                            }
                        }
                    }
                ]
            }
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=batch_update_spreadsheet_request_body
            ).execute()
            
            # Add headers
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{state_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [csv_columns]}
            ).execute()

        # Prepare values
        values = []
        for row in rows:
            row_values = []
            for col in csv_columns:
                row_values.append(row.get(col, ""))
            values.append(row_values)

        print(f"    ✍ Writing {len(values)} rows to '{state_name}' tab...")
        # Append data
        body = {"values": values}
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{state_name}!A:Q",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()

        updates = result.get('updates', {})
        return f"Successfully added {updates.get('updatedRows', len(values))} places to the '{state_name}' tab in Google Sheets."

    except Exception as e:
        return f"Error writing to Google Sheets: {e}"


def execute_sheets_instruction(instruction: str) -> str:
    """Executes generic Google Sheets operations like reading specific cells, writing raw data arrays, or clearing ranges.
    DO NOT use this tool if the user is asking to add or fetch tourist places for a state/city into the sheet (use enrich_state_places for that).
    
    Args:
        instruction (str): The natural language instruction describing the generic sheet operation (e.g. "Read A1:B10", "Clear Sheet1").
    """
    env = _load_env()
    sheet_id = env.get("GOOGLE_SHEETS_ID", "")
    
    if not sheet_id:
        return (
            "❌ Google Sheets ID nahi mila!\n"
            "  .env file me GOOGLE_SHEETS_ID=your_sheet_id_here add karo.\n"
            "  Sheet ID URL me milta hai: docs.google.com/spreadsheets/d/[THIS_PART]/edit"
        )
    
    # Parse instruction with LLM
    print("  🧠 Instruction parse ho rahi hai...")
    raw = _parse_chain.invoke({"instruction": instruction, "sheet_id": sheet_id})
    
    # Extract JSON from response
    import re
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        return f"❌ Instruction parse nahi ho paya.\nLLM response: {raw}"
    
    try:
        action_data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        return f"❌ JSON parse error: {e}\nRaw: {raw}"
    
    action     = action_data.get("action", "read")
    sheet_name = action_data.get("sheet_name", "Sheet1")
    rng        = action_data.get("range", "A1:Z1000")
    values     = action_data.get("values")
    full_range = f"{sheet_name}!{rng}"
    
    print(f"  📊 Action: {action} | Range: {full_range}")
    
    try:
        service = _get_sheet_service()
        sheets  = service.spreadsheets()
        
        if action == "read":
            result = sheets.values().get(spreadsheetId=sheet_id, range=full_range).execute()
            rows = result.get("values", [])
            if not rows:
                return "📊 Sheet mein koi data nahi mila (empty range)."
            lines = [f"📊 Data from {full_range}:"]
            for r in rows:
                lines.append("  | " + " | ".join(str(c) for c in r) + " |")
            return "\n".join(lines)
        
        elif action == "append":
            body = {"values": values or [["(no data)"]]}
            sheets.values().append(
                spreadsheetId=sheet_id, range=full_range,
                valueInputOption="USER_ENTERED", body=body
            ).execute()
            return f"✅ Row append ho gaya: {values}"
        
        elif action == "write":
            body = {"values": values or [["(no data)"]]}
            sheets.values().update(
                spreadsheetId=sheet_id, range=full_range,
                valueInputOption="USER_ENTERED", body=body
            ).execute()
            return f"✅ Data write ho gaya at {full_range}: {values}"
        
        elif action == "clear":
            sheets.values().clear(spreadsheetId=sheet_id, range=full_range).execute()
            return f"✅ Range {full_range} clear ho gaya."
        
        else:
            return f"❌ Unknown action: {action}"
    
    except Exception as e:
        return f"❌ Google Sheets operation fail: {e}"
