# using langchain text splitter

# pyrefly: ignore [missing-import]
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(text_input, chunk_size=500, chunk_overlap=100):
    """
    text_input: str ya list of str — dono handle karega.
    Returns: list of str chunks
    """
    # Agar list aaye toh join karke single string banao
    if isinstance(text_input, list):
        combined = "\n\n".join([t for t in text_input if t and isinstance(t, str)])
    else:
        combined = text_input or ""

    if not combined.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )

    chunks = splitter.split_text(combined)
    return chunks