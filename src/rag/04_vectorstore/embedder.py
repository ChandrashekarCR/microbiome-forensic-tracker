# We need to embed all the informaiton in a vector database. For this we will use the Chroma db

# Import libraries
import json
import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

# Project directory
os.chdir("/home/chandru/binp51/src/rag")

# Configuration
FACTS_PATH = Path("03_extraction/extracted_facts/all_facts.json")
CHROMA_PATH = Path("04_vectorstore/chroma_db")
COLLECTION_NAME = "skane_microbiome_ecology"

# We need to use a biology aware embedding model. This part can be changed with a different tokenizer and the
# correspondin embedding model
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def build_fact_text(fact: dict) -> str:
    """
    Create a rich text representation of a fact for embedding.
    This text is what gets converted into a vector.
    More contect = better retrival
    """

    parts = [
        f"Organism: {fact.get('organism','Unknown')}",
        f"Taxon rank: {fact.get('taxon_rank','')}",
        f"Found in: {fact.get('environment','')}",
    ]

    if fact.get("location") and fact["location"] != "not specified":
        parts.append(f"Location: {fact['location']}")

    if fact.get("condition"):
        parts.append(f"Conditions: {fact['condition']}")

    if fact.get("association_strength"):
        parts.append(f"Association: {fact['association_strength']}")

    if fact.get("source_sentence"):
        parts.append(f"Evidence: {fact['source_sentence']}")

    return " | ".join(parts)


def build_vectorstore():
    """
    Build chromadb collection from extracted facts
    """

    with open(FACTS_PATH) as f:
        print("Loading all the facts")
        all_facts = json.load(f)

    print(f"Embedding {len(all_facts)} facts into ChromaDB...")

    # Initialize ChromaDB (persistent, local)
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Set up embedding function
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

    # Create or reset collection
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},  # Cosine similarity for text
    )

    # Prepare data for batch insert
    ids, documents, metadatas = [], [], []

    for i, fact in enumerate(tqdm(all_facts, desc="Preparing")):
        fact_text = build_fact_text(fact)
        fact_id = f"fact_{i:06d}"

        metadata = {
            "organism": fact.get("organism", "")[:100],
            "taxon_rank": fact.get("taxon_rank", ""),
            "environment": fact.get("environment", "")[:200],
            "location": fact.get("location", "not specified")[:100],
            "association_strength": fact.get("association_strength", ""),
            "confidence": float(fact.get("confidence", 0.5)),
            "pmid": fact.get("pmid", ""),
            "doi": fact.get("doi", ""),
            "year": fact.get("year", ""),
            "paper_title": fact.get("paper_title", "")[:200],
        }

        # ChromaDB requires string metadata values
        metadata = {k: str(v) for k, v in metadata.items()}

        ids.append(fact_id)
        documents.append(fact_text)
        metadatas.append(metadata)

    # Insert in batches (ChromaDB batch limit ~5000)
    BATCH_SIZE = 500
    for start in range(0, len(ids), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(ids))
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        print(f"Added batch {start//BATCH_SIZE + 1}: {end-start} facts")

    print(f"ChromaDB built: {collection.count()} vectors stored")
    print(f"Path: {CHROMA_PATH}")
    return collection


def query_knowledge_base(organism_list: list[str], top_k: int = 10, location_filter: str = None) -> list[dict]:
    """
    Query ChromaDB for environmental context about a list of organisms.
    Used by the forensic pipeline in Step 5.
    """
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    collection = chroma_client.get_collection(name=COLLECTION_NAME, embedding_function=ef)

    # Build rich query text
    query_text = f"Environmental habitat of: {', '.join(organism_list)}"

    # Optional: filter to only Skåne/Sweden papers
    where_filter = None
    if location_filter:
        where_filter = {"location": {"$contains": location_filter}}

    results = collection.query(
        query_texts=[query_text],
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    retrieved = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        retrieved.append(
            {
                "text": doc,
                "metadata": meta,
                "similarity": 1 - dist,  # Convert cosine distance to similarity
            }
        )

    return retrieved


build_vectorstore()
