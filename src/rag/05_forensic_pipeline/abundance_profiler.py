"""
Input  : A DIRECTORY of Bracken rank tables (class/family/genus/order/phylum/species)
         OR a single standardized CSV.
Output : A structured profile output

Expected directory layout (your output):
    11_final_reports/
        kraken_bracken_class.csv
        kraken_bracken_family.csv
        kraken_bracken_genus.csv
        kraken_bracken_order.csv
        kraken_bracken_phylum.csv
        kraken_bracken_species.csv

Each file has columns:
    classifier, clade, tax_id, <sample_id_1>, <sample_id_2>, ...
    e.g.:
    kraken_bracken, Bacteroides fragilis, 817, 0.143, 0.002, ...
"""

# Importing libraries
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
from openai import OpenAI

# Configuration
ROOT = Path("/home/chandru/binp51/src/rag")
# OLLAMA configuration
OLLAMA_HOST = "http://127.0.0.1:11434"  # ollama serve address
OLLAMA_MODEL = "mistral"  # must match: ollama list

# Taxonomic rank priority — most specific first for ChromaDB queries
RANK_PRIORITY = ["species", "genus", "family", "order", "class", "phylum"]
MIN_ABD = 0.001
TOP_TAXA = 50
TOP_K = 15
ENVS = """
    - "sewage / wastewater"
    - "urban garden soil"
    - "agricultural soil"
    - "forest soil"
    - "coastal / marine sediment"
    - "freshwater sediment / riverbed"
    - "indoor dust / built environment"
    - "roadside / urban soil"
    - "wetland / peat"
    - "decomposition / post-mortem soil"

"""
REPORTS_DIR = ROOT / "05_forensic_pipeline/reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

client = OpenAI(
    base_url=f"{OLLAMA_HOST}/v1",
    api_key="ollama",  # Ollama ignores this but client requires it
)

# ── Shim so embedder.py can be imported without circular deps ─────────────────
# (embedder.py lives in 04_vectorstore/, forensic_rag.py in 05_profiling/)

_shim_path = ROOT / "embedder_import_shim.py"
if not _shim_path.exists():
    _shim_path.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent / '04_vectorstore'))\n"
        "from embedder import query_knowledge_base\n",
        encoding="utf-8",
    )

# Import query function from the vectorstore module
sys.path.insert(0, str(ROOT))
from embedder_import_shim import query_knowledge_base  # type: ignore # noqa: E402

# ── Step 1: Parse abundance tables ───────────────────────────────────────────


def _parse_rank_from_filename(filename: str) -> str:
    """
    Infer taxonomic rank from a Bracken output filename.
    Expects filenames like: kraken_bracken_species.csv, kraken_bracken_genus.csv
    """
    name = Path(filename).stem.lower()
    for rank in RANK_PRIORITY:
        if rank in name:
            return rank
    return "unknown"


def load_abundance_tables(tables_input: str | Path) -> pd.DataFrame:
    """
    Load all Bracken rank tables from a directory OR a single CSV file.

    Directory mode (your setup):
        Reads kraken_bracken_class.csv, kraken_bracken_family.csv, ...
        Each file has columns: classifier, clade, tax_id, <sample_id(s)>

    Returns a long-format DataFrame with columns:
        sample_id | taxon | tax_id | abundance | rank

    All ranks are kept — the caller decides which ranks to use per query.
    """
    tables_input = Path(tables_input)
    fixed_cols = ["classifier", "clade", "tax_id"]

    if tables_input.is_dir():
        csv_files = sorted(tables_input.glob("kraken_bracken_*.csv"))
        if not csv_files:
            # Fall back to any CSV in the directory
            csv_files = sorted(tables_input.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {tables_input}")
    else:
        csv_files = [tables_input]

    frames: list[pd.DataFrame] = []

    for csv_path in csv_files:
        rank = _parse_rank_from_filename(csv_path.name)
        df = pd.read_csv(csv_path, header=0)

        sample_cols = [c for c in df.columns if c not in fixed_cols]
        if not sample_cols:
            print(f"[WARN] No sample columns in {csv_path.name}, skipping")
            continue

        # Melt wide → long
        long = df.melt(
            id_vars=["clade", "tax_id"],
            value_vars=sample_cols,
            var_name="sample_id",
            value_name="abundance",
        )
        long = long.rename(columns={"clade": "taxon"})
        long["abundance"] = pd.to_numeric(long["abundance"], errors="coerce").fillna(0.0)
        long["rank"] = rank
        frames.append(long)
        print(f"Loaded {csv_path.name:45s}  rank={rank:8s}  rows={len(df)}")

    if not frames:
        raise ValueError("Could not load any Bracken tables")

    combined = pd.concat(frames, ignore_index=True)
    print(f"Total rows (all ranks, all samples): {len(combined)}")
    return combined


def get_top_taxa(
    long_df: pd.DataFrame,
    sample_id: str,
    ranks: list[str] | None = None,
) -> list[dict]:
    """
    Return the top abundant taxa for a sample, across all (or selected) ranks.

    Strategy:
      - Filter to rows for this sample above MIN_ABD
      - For each rank, take the top TOP_TAXA entries
      - Return a combined list sorted by (rank_priority, abundance desc)
        so the most specific and most abundant taxa appear first

    Returns list of dicts:
        {taxon, tax_id, abundance, rank}
    """
    ranks = ranks or RANK_PRIORITY

    sample_df = long_df[(long_df["sample_id"] == sample_id) & (long_df["abundance"] >= MIN_ABD) & (long_df["rank"].isin(ranks))].copy()

    if sample_df.empty:
        print(f"  [WARN] No taxa above MIN_ABD={MIN_ABD} for sample {sample_id}")
        return []

    # Per-rank top-N, then combine and de-duplicate by taxon name
    rank_order = {r: i for i, r in enumerate(RANK_PRIORITY)}
    sample_df["rank_order"] = sample_df["rank"].map(lambda r: rank_order.get(r, 99))

    # Sort: most specific rank first, then by abundance descending
    sample_df = sample_df.sort_values(
        ["rank_order", "abundance"],
        ascending=[True, False],
    )

    # Take top TOP_TAXA per rank, then cap total at TOP_TAXA * len(ranks)
    per_rank = sample_df.groupby("rank", group_keys=False).apply(lambda g: g.nlargest(TOP_TAXA, "abundance"))

    return [
        {
            "taxon": row["taxon"],
            "tax_id": str(row["tax_id"]),
            "abundance": float(row["abundance"]),
            "rank": row["rank"],
        }
        for _, row in per_rank.iterrows()
    ]


# Step 2: Retrieve ecological context


def retrieve_ecological_context(taxa: list[dict]) -> list[dict]:
    """
    Query ChromaDB for ecological facts relevant to the sample's taxa.

    Query strategy (multi-rank):
      1. PRIMARY query  — species + genus names (most specific, best matches)
      2. CONTEXT query  — family + order names (broader context)
      3. PHYLUM query   — phylum names (fallback for under-studied taxa)

    All results are deduplicated and returned together, sorted by similarity.
    """
    abundance_map = {t["taxon"]: t["abundance"] for t in taxa}

    # Group taxa by rank
    by_rank: dict[str, list[str]] = {r: [] for r in RANK_PRIORITY}
    for t in taxa:
        by_rank.get(t["rank"], by_rank["phylum"]).append(t["taxon"])

    all_results: list[dict] = []
    seen_texts: set[str] = set()

    # Query tier 1: species + genus (high specificity)
    tier1 = by_rank["species"] + by_rank["genus"]
    if tier1:
        r1 = query_knowledge_base(tier1, top_k=TOP_K)
        for r in r1:
            if r["text"] not in seen_texts:
                seen_texts.add(r["text"])
                all_results.append(r)

    # Query tier 2: family + order (moderate specificity)
    tier2 = by_rank["family"] + by_rank["order"]
    if tier2:
        r2 = query_knowledge_base(tier2, top_k=TOP_K // 2)
        for r in r2:
            if r["text"] not in seen_texts:
                seen_texts.add(r["text"])
                all_results.append(r)

    # Query tier 3: class + phylum (broad fallback)
    tier3 = by_rank["class"] + by_rank["phylum"]
    if tier3 and len(all_results) < TOP_K:
        r3 = query_knowledge_base(tier3, top_k=TOP_K // 3)
        for r in r3:
            if r["text"] not in seen_texts:
                seen_texts.add(r["text"])
                all_results.append(r)

    # Attach sample abundance to each result (for environment scoring)
    for r in all_results:
        meta_org = r["metadata"].get("organism", "").lower()
        matched_abundance = 0.0
        for taxon, abd in abundance_map.items():
            if taxon.lower() in meta_org or meta_org in taxon.lower():
                matched_abundance = abd
                break
        r["query_abundance"] = matched_abundance

    # Sort by similarity descending
    all_results.sort(key=lambda x: x["similarity"], reverse=True)
    return all_results


# ── Step 3: Score environments ────────────────────────────────────────────────


def _map_to_canonical(raw_env: str) -> str | None:
    """Map a free-text environment description to one of the canonical ENVS."""
    mapping = {
        "sewage": "sewage / wastewater",
        "wastewater": "sewage / wastewater",
        "effluent": "sewage / wastewater",
        "garden": "urban garden soil",
        "park": "urban garden soil",
        "urban soil": "urban garden soil",
        "urban garden": "urban garden soil",
        "agricultural": "agricultural soil",
        "farmland": "agricultural soil",
        "crop": "agricultural soil",
        "forest": "forest soil",
        "woodland": "forest soil",
        "beech": "forest soil",
        "oak": "forest soil",
        "rhizosphere": "forest soil",
        "litter": "forest soil",
        "coastal": "coastal / marine sediment",
        "marine": "coastal / marine sediment",
        "sediment": "coastal / marine sediment",
        "baltic": "coastal / marine sediment",
        "freshwater": "freshwater sediment / riverbed",
        "river": "freshwater sediment / riverbed",
        "lake": "freshwater sediment / riverbed",
        "stream": "freshwater sediment / riverbed",
        "indoor": "indoor dust / built environment",
        "dust": "indoor dust / built environment",
        "house": "indoor dust / built environment",
        "building": "indoor dust / built environment",
        "roadside": "roadside / urban soil",
        "road": "roadside / urban soil",
        "traffic": "roadside / urban soil",
        "wetland": "wetland / peat",
        "peat": "wetland / peat",
        "bog": "wetland / peat",
        "marsh": "wetland / peat",
        "decomposit": "decomposition / post-mortem soil",
        "post-mortem": "decomposition / post-mortem soil",
        "thanato": "decomposition / post-mortem soil",
        "corpse": "decomposition / post-mortem soil",
    }
    for keyword, canonical in mapping.items():
        if keyword in raw_env:
            return canonical
    return None


def score_environments(retrieved: list[dict]) -> dict[str, float]:
    """
    Assign a probability score to each canonical environment category.

    Score formula per fact:
        score = similarity × confidence × (1 + 3 × abundance)

    The abundance bonus means that highly abundant taxa in the sample
    carry more weight than rare ones.

    Returns a dict {environment: normalised_probability}.
    """
    env_scores: dict[str, float] = defaultdict(float)

    for fact in retrieved:
        env_raw = fact["metadata"].get("environment", "").lower()
        similarity = float(fact.get("similarity", 0.0))
        confidence = float(fact["metadata"].get("confidence", "0.5"))
        abundance = float(fact.get("query_abundance", 0.0))

        # Map the raw environment string to the nearest canonical category
        canonical = _map_to_canonical(env_raw)
        if canonical:
            score = similarity * confidence * (1.0 + 3.0 * abundance)
            env_scores[canonical] += score

    # Ensure all canonical environments are present (even with 0 score)
    for env in ENVS:
        if env not in env_scores:
            env_scores[env] = 0.0

    total = sum(env_scores.values())
    if total == 0:
        # No evidence at all — return uniform distribution
        n = len(ENVS)
        return {env: round(1.0 / n, 4) for env in ENVS}

    return {env: round(score / total, 4) for env, score in sorted(env_scores.items(), key=lambda x: x[1], reverse=True)}


# ── Step 4: LLM forensic narrative ────────────────────────────────────────────

FORENSIC_SYSTEM = """\
You are a forensic microbiologist writing an expert witness report for Swedish police.
Your language is precise, evidence-based, and non-speculative.
You highlight the most diagnostic taxa and the strongest environmental evidence.
Always cite PMIDs when available.
"""

FORENSIC_USER = """\
Write a forensic microbiome profile for the sample below.

SAMPLE ID: {sample_id}
ANALYSIS DATE: {today}

TOP TAXA (relative abundance):
{taxa_table}

ENVIRONMENT PROBABILITY SCORES:
{env_scores}

SUPPORTING ECOLOGICAL EVIDENCE (from literature):
{evidence_block}

Write a structured forensic profile with these sections:
1. Executive Summary (2-3 sentences for non-experts)
2. Primary Environment Match (most likely environment with confidence)
3. Secondary Matches (other plausible environments)
4. Key Diagnostic Taxa (which organisms most strongly indicate the top environment)
5. Limitations and Caveats
6. Conclusion

Format: plain text, professional, suitable for a police report.
"""


def generate_forensic_narrative(
    sample_id: str,
    taxa: list[dict],
    env_probs: dict[str, float],
    retrieved: list[dict],
) -> str:
    """Call Ollama to write the narrative section of the forensic report."""

    # Build taxa table — group by rank for clarity
    taxa_by_rank: dict[str, list] = {r: [] for r in RANK_PRIORITY}
    for t in taxa:
        taxa_by_rank.get(t.get("rank", "species"), taxa_by_rank["species"]).append(t)

    taxa_lines: list[str] = []
    for rank in RANK_PRIORITY:
        entries = taxa_by_rank[rank]
        if not entries:
            continue
        taxa_lines.append(f"  [{rank.upper()}]")
        for t in entries:
            taxa_lines.append(f"    {t['taxon']:<50}  {t['abundance']:.4f}  ({t['abundance']*100:.2f}%)")
    taxa_table = "\n".join(taxa_lines)

    # Build env scores table (top 5 only to keep prompt short)
    top_envs = list(env_probs.items())[:5]
    env_scores = "\n".join(f"  {env:<40}  {prob*100:.1f}%" for env, prob in top_envs)

    # Build evidence block (top 8 most similar facts)
    top_evidence = sorted(retrieved, key=lambda x: x["similarity"], reverse=True)[:8]
    evidence_block = "\n".join(
        f"  [{r['metadata'].get('pmid', 'N/A')}] "
        f"{r['metadata'].get('organism', '?')} "
        f"→ {r['metadata'].get('environment', '?')} "
        f"(similarity: {r['similarity']:.2f})"
        for r in top_evidence
    )

    prompt = FORENSIC_USER.format(
        sample_id=sample_id,
        today=str(date.today()),
        taxa_table=taxa_table,
        env_scores=env_scores,
        evidence_block=evidence_block,
    )

    response = client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": FORENSIC_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    return response.choices[0].message.content.strip()


# Step 5: Assemble and save report


def build_report(
    sample_id: str,
    taxa: list[dict],
    env_probs: dict[str, float],
    retrieved: list[dict],
    narrative: str,
) -> dict:
    """Assemble the full structured report dict."""
    top_env = max(env_probs, key=env_probs.get)

    return {
        "sample_id": sample_id,
        "analysis_date": str(date.today()),
        "primary_environment": top_env,
        "primary_probability": env_probs[top_env],
        "environment_scores": env_probs,
        "top_taxa": taxa,
        "n_literature_facts": len(retrieved),
        "narrative": narrative,
        "evidence_summary": [
            {
                "organism": r["metadata"].get("organism", ""),
                "environment": r["metadata"].get("environment", ""),
                "location": r["metadata"].get("location", ""),
                "pmid": r["metadata"].get("pmid", ""),
                "similarity": r["similarity"],
            }
            for r in sorted(retrieved, key=lambda x: x["similarity"], reverse=True)[:10]
        ],
    }


def _write_text_report(report: dict, path: Path) -> None:
    """Write a plain-text version of the report for direct police use."""
    lines = [
        "=" * 65,
        "FORENSIC MICROBIOME PROFILE",
        "=" * 65,
        f"Sample ID      : {report['sample_id']}",
        f"Analysis Date  : {report['analysis_date']}",
        f"Primary Match  : {report['primary_environment']} " f"({report['primary_probability']*100:.1f}% probability)",
        "",
        "ENVIRONMENT PROBABILITY SCORES:",
        *[f"  {env:<42} {prob*100:.1f}%" for env, prob in report["environment_scores"].items()],
        "",
        "TOP TAXA (by rank):",
        *[f"  [{t.get('rank','?'):8s}]  {t['taxon']:<50} {t['abundance']*100:.3f}%" for t in report["top_taxa"]],
        "",
        "─" * 65,
        "FORENSIC NARRATIVE:",
        "─" * 65,
        report["narrative"],
        "",
        "─" * 65,
        "LITERATURE EVIDENCE (top 10 by relevance):",
        "─" * 65,
        *[f"  PMID {e['pmid']:>10} | {e['organism']:<35} → {e['environment']}" for e in report["evidence_summary"]],
        "=" * 65,
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# Main entry point


def profile_sample(table_path: str | Path, sample_id: str | None = None) -> dict:
    """
    Generate a forensic profile for one sample.

    Args:
        table_path : Path to a DIRECTORY containing kraken_bracken_*.csv files
                     OR a single standardized Bracken CSV.
        sample_id  : Sample column name (e.g. 'zr23059_100').
                     If None, profiles ALL samples found in the tables.

    Returns:
        Report dict (also saved to reports/ directory).
    """
    table_path = Path(table_path)
    print(f"Loading tables from: {table_path}")
    long_df = load_abundance_tables(table_path)

    if sample_id is None:
        # Profile all samples in the table
        sample_ids = long_df["sample_id"].unique().tolist()
    else:
        sample_ids = [sample_id]

    reports = []
    for sid in sample_ids:
        print(f"\n{'='*60}")
        print(f"Profiling sample: {sid}")
        print(f"{'='*60}")

        # Step 1
        taxa = get_top_taxa(long_df, sid)
        print(f"Step 1: {len(taxa)} taxa above abundance threshold {MIN_ABD}")

        # Step 2
        retrieved = retrieve_ecological_context(taxa)
        print(f"Step 2: Retrieved {len(retrieved)} ecological facts from ChromaDB")

        # Step 3
        env_probs = score_environments(retrieved)
        top_env = max(env_probs, key=env_probs.get)
        print(f"Step 3: Top environment -> '{top_env}'  ({env_probs[top_env]*100:.1f}%)")

        # Step 4
        print("Step 4: Generating forensic narrative with Ollama...")
        narrative = generate_forensic_narrative(sid, taxa, env_probs, retrieved)

        # Step 5
        report = build_report(sid, taxa, env_probs, retrieved, narrative)
        reports.append(report)

        # Save JSON
        json_path = REPORTS_DIR / f"{sid}_forensic_profile.json"
        with open(json_path, "w") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

        # Save human-readable text
        txt_path = REPORTS_DIR / f"{sid}_forensic_profile.txt"
        _write_text_report(report, txt_path)

        print(f"\nReports saved:\n  {json_path}\n  {txt_path}")

    return reports if len(reports) > 1 else reports[0]


profile_sample("/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/11_final_reports")
