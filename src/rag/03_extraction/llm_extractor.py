# The raw chunks contain everything. We will use an LLM to extract only ecological location facts.
# Uses LOCAL OLLAMA — no API key, no rate limits, runs on LUNARC GPU

# Import libraries
import json
import os
import re
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

# OLLAMA configuration
OLLAMA_HOST = "http://127.0.0.1:11434"  # ollama serve address
OLLAMA_MODEL = "mistral"  # must match: ollama list


# Project directory
os.chdir("/home/chandru/binp51/src/rag")

CHUNKS_DIR = Path("02_chunking/chunks")
FACTS_DIR = Path("03_extraction/extracted_facts")
FACTS_DIR.mkdir(exist_ok=True, parents=True)

client = OpenAI(
    base_url=f"{OLLAMA_HOST}/v1",
    api_key="ollama",  # Ollama ignores this but client requires it
)


def _check_ollama_running():
    """Fail fast with a clear message if ollama server isn't up."""
    import urllib.request

    try:
        urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3)
    except Exception as e:
        raise RuntimeError(
            f"Ollama server is not running at {OLLAMA_HOST}\n"
            f"Start it with:\n"
            f"  OLLAMA_MODELS=$HOME/ollama_models "
            f"/home/chandru/ollama/bin/ollama serve &"
        ) from e


# Prompt Engineering
# Here we encode the domain expertise role into the system.
EXTRACTION_SYSTEM_PROMPT = """You are a forensic environmental microbiologist specializing 
in Scandinavian ecosystems, particularly the Skåne region of Sweden.

Your task is to extract ONLY ecological habitat associations from scientific text.
Specifically, you extract facts that answer: 
"Which microorganisms (bacteria, fungi, archaea, eukaryotes) are found WHERE?"

OUTPUT FORMAT (strict JSON array):
[
  {
    "organism": "Genus species OR higher taxon (e.g., Pseudomonas fluorescens, Clostridiales)",
    "taxon_rank": "species|genus|family|order|class|phylum",
    "environment": "specific environment type (e.g., garden soil, sewage, forest floor, coastal sediment)",
    "location": "geographic location if mentioned (e.g., Sweden, Skåne, Malmö, Scandinavia, or 'not specified')",
    "condition": "environmental conditions if mentioned (e.g., pH 6.2, sun-exposed, anaerobic, near oak trees)",
    "association_strength": "dominant|common|present|rare",
    "source_sentence": "exact sentence from text that supports this fact",
    "confidence": 0.0-1.0
  }
]

RULES:
- Only include facts about organism-environment relationships
- Skip methodological details, author information, funding
- If no relevant facts exist, return an empty array []
- Be conservative: only extract what is explicitly stated
- Include geographic location even if it's just "Scandinavia" or "northern Europe"
- For trees/plants, extract their associated soil microbiome if mentioned
"""

EXTRACTION_USER_TEMPLATE = """Extract ecological habitat associations from this scientific text chunk.

PAPER: {title}
SECTION: {section}
TEXT:
{text}

Return only the JSON array. No explanation needed."""


def _parse_json_response(raw: str) -> list[dict]:
    """
    Robustly parse LLM JSON output.
    Local models (unlike GPT-4) often wrap output in ```json ... ```
    or add sentences before the array. This strips all of that.
    """
    # Strip markdown code fences
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)
    raw = raw.strip()

    # Find the JSON array boundaries (ignore any preamble text)
    start = raw.find("[")
    end = raw.rfind("]") + 1

    if start == -1 or end == 0:
        return []  # No array found at all

    try:
        parsed = json.loads(raw[start:end])
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def extract_facts_from_chunk(chunk: dict) -> list[dict]:
    """Use local Ollama to extract ecological facts from one chunk."""

    prompt = EXTRACTION_USER_TEMPLATE.format(
        title=chunk["metadata"].get("title", "Unknown"),
        section=chunk.get("section", "unknown"),
        text=chunk["text"],
    )

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
            # NOTE: do NOT pass response_format={"type":"json_object"} here
            # Ollama/mistral ignores it and it can cause errors on some versions
        )

        raw = response.choices[0].message.content
        facts = _parse_json_response(raw)

        # Enrich each fact with source metadata
        for fact in facts:
            fact["chunk_id"] = chunk["chunk_id"]
            fact["pmid"] = chunk["pmid"]
            fact["paper_title"] = chunk["metadata"].get("title", "")
            fact["doi"] = chunk["metadata"].get("doi", "")
            fact["year"] = chunk["metadata"].get("year", "")

        return facts

    except Exception as e:
        print(f"  Extraction error (chunk {chunk['chunk_id']}): {e}")
        return []


def run_extraction():
    """
    Extract facts from all chunks.
    No rate limiting — local Ollama has no API quotas.
    Checkpoint resume — safe to kill and restart on SLURM.
    """

    # Fail fast if ollama isn't running
    _check_ollama_running()
    print(f"Ollama server OK at {OLLAMA_HOST}")
    print(f"Model: {OLLAMA_MODEL}\n")

    with open(CHUNKS_DIR / "all_chunks.json") as f:
        all_chunks = json.load(f)

    facts_path = FACTS_DIR / "all_facts.json"
    checkpoint_path = FACTS_DIR / "checkpoint_done_ids.json"

    # Resume from checkpoint if it exists
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            done_ids: set[str] = set(json.load(f))
        with open(facts_path) as f:
            all_facts: list[dict] = json.load(f)
        print(
            f"Resuming - {len(done_ids)} chunks already processed, "
            f"{len(all_facts)} facts loaded."
        )
    else:
        done_ids: set[str] = set()
        all_facts: list[dict] = []

    remaining = [
        c
        for c in all_chunks
        if c["chunk_id"] not in done_ids and c.get("token_count", 0) >= 30
    ]
    print(
        f"Processing {len(remaining)} remaining chunks "
        f"(total {len(all_chunks)}, skipped short/done)...\n"
    )

    for chunk in tqdm(remaining, desc="Extracting"):
        facts = extract_facts_from_chunk(chunk)
        all_facts.extend(facts)
        done_ids.add(chunk["chunk_id"])

        # Checkpoint every 10 chunks — SLURM kill-safe
        if len(done_ids) % 10 == 0:
            with open(facts_path, "w") as f:
                json.dump(all_facts, f, indent=2, ensure_ascii=False)
            with open(checkpoint_path, "w") as f:
                json.dump(list(done_ids), f)

    # Final save
    with open(facts_path, "w") as f:
        json.dump(all_facts, f, indent=2, ensure_ascii=False)
    with open(checkpoint_path, "w") as f:
        json.dump(list(done_ids), f)

    # Summary statistics
    total = len(all_facts)

    print(f"\n{'='*50}")
    print(f"Extracted     : {total} ecological facts")
    print(f"Saved to      : {facts_path}")
    print(f"{'='*50}")

    return all_facts


run_extraction()
