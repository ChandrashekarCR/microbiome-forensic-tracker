# This breaks down the research paper into context aware chunks using docling.

# Import libraries
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.chunking import HybridChunker
from transformers import AutoTokenizer
import os

# Project directory
os.chdir("/home/chandru/binp51/src/rag")
# Config
INPUT_METADATA = Path("01_data_retrival/pubmed_papers/metadata.json")
CHUNKS_DIR = Path("02_chunking/chunks")
CHUNKS_DIR.mkdir(exist_ok=True, parents=True)


# Use the same tokenizer as your embedding model (TOEKNIZER == EMBEDDING MODEL)
TOKENIZER_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MAX_TOKENS = 256  # Optimal for RAG: not too large, not too small


def _jats_xml_to_markdown(xml_path: Path) -> str:
    """
    Extract structured text from a PMC JATS/NXML file and format as Markdown.
    PMC Entrez efetch returns pmc-articleset as the root element containing
    one or more <article> elements in JATS format.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # pmc-articleset wraps <article>; fall back to root if not found
        article_el = root.find('.//article')
        article = article_el if article_el is not None else root
        sections: list[str] = []

        # Title 
        title_el = article.find('.//article-title')
        if title_el is not None:
            t = ''.join(title_el.itertext()).strip()
            if t:
                sections.append(f"# {t}")

        # Abstract
        for abstract_el in article.findall('.//abstract'):
            sections.append("## Abstract")
            for elem in abstract_el.iter():
                if elem.tag == 'title':
                    t = ''.join(elem.itertext()).strip()
                    if t:
                        sections.append(f"### {t}")
                elif elem.tag == 'p':
                    text = ''.join(elem.itertext()).strip()
                    if text:
                        sections.append(text)

        # Body 
        body_el = article.find('.//body')
        if body_el is not None:
            def _sec_to_md(sec_el: ET.Element, depth: int = 2) -> list[str]:
                parts: list[str] = []
                sec_title = sec_el.find('title')
                if sec_title is not None:
                    t = ''.join(sec_title.itertext()).strip()
                    if t:
                        parts.append(f"\n{'#' * depth} {t}")
                for child in sec_el:
                    if child.tag == 'p':
                        text = ''.join(child.itertext()).strip()
                        if text:
                            parts.append(text)
                    elif child.tag == 'sec':
                        parts.extend(_sec_to_md(child, depth + 1))
                return parts

            for sec in body_el.findall('sec'):
                sections.extend(_sec_to_md(sec))

        return '\n\n'.join(filter(None, sections))

    except Exception as e:
        print(f"  Warning: XML parsing failed for {xml_path.name}: {e}")
        return ""


def process_document(source: str | Path, pmid: str, metadata: dict) -> list[dict]:
    """
    Convert a document to semantic chunks using Docling
    """

    source = Path(source)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    # Only allow formats we will actually feed to Docling
    converter = DocumentConverter(
        allowed_formats=[InputFormat.MD, InputFormat.PDF, InputFormat.HTML]
    )
    chunker = HybridChunker(
        tokenizer=tokenizer,
        max_tokens=MAX_TOKENS,
        merge_peers=True,
    )

    temp_file: Path | None = None
    try:
        suffix = source.suffix.lower()

        if suffix == '.xml':
            # PMC JATS XML -> extract text -> temp Markdown for Docling
            md_text = _jats_xml_to_markdown(source)
            if not md_text.strip():
                raise ValueError(f"No text could be extracted from {source.name}")
            temp_file = CHUNKS_DIR / f"_{pmid}_jats_temp.md"
            temp_file.write_text(md_text, encoding="utf-8")
            convert_source = temp_file

        elif suffix == '.txt':
            # Plain text -> temp Markdown (.txt is not supported by Docling)
            temp_file = CHUNKS_DIR / f"_{pmid}_txt_temp.md"
            temp_file.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            convert_source = temp_file

        else:
            convert_source = source

        print(f"Converting: {convert_source.name}")
        result = converter.convert(str(convert_source))
        doc = result.document

    finally:
        # Always clean up temp files even if conversion fails
        if temp_file is not None and temp_file.exists():
            temp_file.unlink()

    # Chunk the document
    chunks = list(chunker.chunk(doc))

    enriched_chunks = []
    for i, chunk in enumerate(chunks):
        try:
            page = chunk.meta.doc_items[0].prov[0].page_no if chunk.meta.doc_items else None
        except (IndexError, AttributeError):
            page = None

        enriched_chunks.append({
            "chunk_id": f"{pmid}_chunk_{i:04d}",
            "pmid": pmid,
            "text": chunk.text,
            "token_count": len(tokenizer.encode(chunk.text)),
            "page": page,
            "section": _infer_section(chunk),
            # Paper-level metadata for filtering
            "metadata": {
                "title": metadata.get("title", ""),
                "journal": metadata.get("journal", ""),
                "year": metadata.get("year", ""),
                "doi": metadata.get("doi", ""),
                "query_source": metadata.get("query_source", ""),
            }
        })

    return enriched_chunks


def _infer_section(chunk) -> str:
    """Try to detect what section of the paper the chunk is from."""
    text_lower = chunk.text.lower()
    if any(kw in text_lower for kw in ["abstract", "summary"]):
        return "abstract"
    elif any(kw in text_lower for kw in ["method", "material", "protocol"]):
        return "methods"
    elif any(kw in text_lower for kw in ["result", "found", "detected", "observed"]):
        return "results"
    elif any(kw in text_lower for kw in ["discuss", "conclude", "suggest"]):
        return "discussion"
    return "general"

def process_all_documents():
    """
    Process all papers from metadata
    """

    with open(INPUT_METADATA) as f:
        all_papers = json.load(f)

    all_chunks = []

    for pmid, paper in all_papers.items():
        print(f"Processing PMID: {pmid}: {paper.get('title','')[:60]}...")

        # Use the full text if available, else use the abstract as pseudo document
        if paper.get('full_text_path') and Path(paper['full_text_path']).exists():
            source = paper['full_text_path']
        
        else:
            # Create a tempory text file from abstract
            abstract_text = f"""
                                Title: {paper.get('title', '')}
                                Journal: {paper.get('journal', '')}
                                Year: {paper.get('year', '')}

                                Abstract:
                                {paper.get('abstract', '')}
                            """.strip()
            
            temp_path = CHUNKS_DIR / f"{pmid}_abstract.md"
            temp_path.write_text(abstract_text, encoding="utf-8")
            source = temp_path


        try:
            chunks = process_document(source, pmid, paper)
            all_chunks.extend(chunks)

            # Save per paper chunks
            chunk_path = CHUNKS_DIR / f"{pmid}_chunks.json"
            with open(chunk_path, "w") as f:
                json.dump(chunks, f, indent=2)
            
            print(f"Produced {len(chunks)} chunks")
        
        except Exception as e:
            print(f" Failed: {e}")
    
    # Save all chunks together
    all_chunks_path = CHUNKS_DIR / "all_chunks.json"
    with open(all_chunks_path, "w") as f:
        json.dump(all_chunks, f, indent=2)
    
    print(f"Total chunks: {len(all_chunks)}")
    return all_chunks

process_all_documents()