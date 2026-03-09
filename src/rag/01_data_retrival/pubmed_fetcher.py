# This script is used to get releavant research papers from PubMed

# Import libraries
import os
import time
import json
import yaml
import requests
from pathlib import Path
from Bio import Entrez
from dotenv import load_dotenv

load_dotenv()

# Root directory
os.chdir("/home/chandru/binp51")

# Configuration
Entrez.email = "ch1131ch-s@student.lu.se"
Entrez.api_key = os.getenv("NCBI_API_KEY")

# Working directory
os.chdir("./src/rag")
OUTPUT_DIR = Path("01_data_retrival/pubmed_papers")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Functions
def search_pubmed(query: str, max_results: int=30) -> list[str]:
    """
    Search Pubmed return list of PMIDs
    """
    handle = Entrez.esearch(
        db="pubmed",
        term=query,
        retmax = max_results,
        sort = "relavance"
    )

    record = Entrez.read(handle)
    handle.close()
    return record["IdList"]

def fetch_paper_metadata(pmid: str) -> dict:
    """
    Fetch full metadata for a single paper.
    """
    handle = Entrez.efetch(
        db="pubmed",
        id = pmid,
        rettype = "xml",
        retmode = "xml"
    )
    records = Entrez.read(handle)
    handle.close()

    try:
        article = records["PubmedArticle"][0]
        medline = article["MedlineCitation"]
        article_data = medline["Article"]
    
        # Extract abstract text
        abstract = ""
        if "Abstract" in article_data:
            abstract_texts = article_data["Abstract"].get("AbstractText", [])
            if isinstance(abstract_texts, list):
                abstract = " ".join(str(t) for t in abstract_texts)
            else:
                abstract = str(abstract_texts)
        
        # Extract DOI
        doi = ""
        for id_obj in article.get("PubmedData", {}).get("ArticleIdList", []):
            if id_obj.attributes.get("IdType") == "doi":
                doi = str(id_obj)
                break
        
        return {
            "pmid": pmid,
            "title": str(article_data.get("ArticleTitle", "")),
            "abstract": abstract,
            "doi": doi,
            "journal": str(article_data.get("Journal", {}).get("Title", "")),
            "year": str(medline.get("DateCompleted", {}).get("Year", "Unknown"))
        }

    except Exception as e:
        print(f"Error parsing PMID {pmid}: {e}")
        return {}
    

def download_full_text_pmc(pmid:str) -> str | None:
    """
    Try to get full text from PubMed Central (open access only)
    """

    # First fint the PMCID
    handle = Entrez.elink(dbfrom="pubmed", db = "pmc", id = pmid)
    record = Entrez.read(handle)
    handle.close()

    try:
        pmcids = record[0]["LinkSetDb"][0]["Link"]
        if not pmcids:
            return None
        pmcid = pmcids[0]["Id"]
        
        # Fetch full XML text from PMC
        handle = Entrez.efetch(db="pmc", id=pmcid, rettype="xml", retmode="xml")
        full_text = handle.read()
        handle.close()
        
        # Save raw XML
        xml_path = OUTPUT_DIR / f"PMC{pmcid}.xml"
        with open(xml_path, "wb") as f:
            f.write(full_text)
        
        return str(xml_path)
    except (IndexError, KeyError):
        return None  # Not in PMC (not open access)

def run_retrival(queries_file: str = "./01_data_retrival/queries.yaml", max_per_query: int = 10):
    """
    Main retrival section
    """
    with open(queries_file) as f:
        config = yaml.safe_load(f)
    
    all_papers = {}
    metadata_path = OUTPUT_DIR / "metadata.json"

    for query in config['queries']:
        print(f"Searching: {query}")
        pmids = search_pubmed(query, max_results=5)
        print(f"Found {len(pmids)} papers")

        for pmid in pmids:
            if pmid in all_papers:
                continue # Skip duplicates

            print(f"Fetching PMID {pmid}...")
            meta = fetch_paper_metadata(pmid)
            
            if meta:
                # Try to get the full text
                full_text_path = download_full_text_pmc(pmid)
                meta['full_text_path'] = full_text_path
                meta['query_source'] = query
                all_papers[pmid] = meta
            
            time.sleep(0.34)

    with open(metadata_path, "w") as f:
        json.dump(all_papers, f, indent=2)

    print(f"Retrieved {len(all_papers)} unique papers")
    print(f"Metadata saved to {metadata_path}")

    return all_papers
            
        

papers = run_retrival()
print(papers)