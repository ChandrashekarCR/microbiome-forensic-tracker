# This breaks down the research paper into context aware chunks using docling.

# Import libraries
import json
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from transformers import AutoTokenizer
import os

# Root directory
os.chdir("/home/chandru/binp51/src/rag")
# Config
INPUT_METADATA = Path("01_data_retrival/pubmed_papers/metadata.json")
CHUNKS_DIR = Path("02_chunking/chunks")
CHUNKS_DIR.mkdir(exist_ok=True, parents=True)


# Use the same tokenizer as your embedding model (TOEKNIZER == EMBEDDING MODEL)
TOKENIZER_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MAX_TOKENS = 256  # Optimal for RAG: not too large, not too small

def process_document(source: str | Path, pmid: str, metadata: dict) -> list[dict]:
    """
    Convert a document to semantic chunks using Docling
    """

    convertor = DocumentConverter()
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    chunker = HybridChunker(
                tokenizer=tokenizer,
                max_tokens = MAX_TOKENS,
                merge_peers= True # Merge short adjacent chunks
    )

    # Convert document (handles PDF, XML, DOCX, HTML, etc.)
    print(f"Converting: {source}")
    result = convertor.convert(str(source))
    doc = result.document

    # Chunk the document
    chunks = list


process_document()