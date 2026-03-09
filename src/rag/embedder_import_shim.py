import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '04_vectorstore'))
from embedder import query_knowledge_base
