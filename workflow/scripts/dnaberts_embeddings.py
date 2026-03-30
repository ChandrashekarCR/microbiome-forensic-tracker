import os
import sys
import torch
import pandas as pd
import numpy as np
from Bio import SeqIO
from transformers import pipeline
from transformers import AutoTokenizer, AutoModel
from transformers import pipeline
from pathlib import Path
import json
from tqdm import tqdm

# DNABERT-S model name
MODEL_NAME = "zhihan1996/DNABERT-S"

class DNABERTSContigEmbedder:
    """
    Generate DNABERT=S embedding for metagenomic assembled contigs.
    """

    def __init__(self,model_name=MODEL_NAME, device="cuda"):
        # Resolve device: use cuda only if available
        if device == "cuda":
            dev_str = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            dev_str = device
            
        self.device = torch.device(dev_str)
        print(f"Loading DNABERT-S on {self.device}...")

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)

        # Load the model and move to device
        self.model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True, low_cpu_mem_usage=False).to(self.device)

        # Set to evaluation mode
        self.model.eval()

        print(f"Model loaded successfully")
        print(f"Model has {sum(p.numel() for p in self.model.parameters()):,} parameters.")

    def create_windows(self, sequence, max_length=512, overlap=0.5):
        """
        Split a sequence into overlapping windows.

        Arguments:
            sequence: DNA contigs after assembly
            max_length=512 (according to the DNA-BERT-S paper)
            overlap: 50%
        """

        stride = int(max_length * (1 - overlap))
        windows = []

        # Approximate: 1 token 1 bp for DNA sequeces
        for start in range(0,len(sequence),stride):
            end = min(start + max_length, len(sequence))
            windows.append(sequence[start:end])

            # Stop if we have reached the end
            if end == len(sequence):
                break
        
        return windows
    
    def embed_sequence(self, sequence, max_length=512, overlap=0.5):
        """
        Generate embedding for a single sequence.
        For long sequences, uses windowing with overlap.
        
        Args:
            sequence: DNA sequence string
            max_length: Maximum sequence length
            overlap: Overlap ratio for windowing
        
        Returns:
            np.ndarray: Embedding vector (768-dim for DNABERT-S)
        """

        # If sequence fits, process directly
        if len(sequence) <= max_length:
            windows = [sequence]
        
        else:
            # Create overlapping windows
            windows = self.create_windows(sequence, max_length, overlap)

        window_embeddings = []

        for window in windows:
            # Tokenize each window
            inputs = self.tokenizer(window, return_tensors="pt", truncation=False,
                                    max_length=max_length, padding='max_length', return_attention_mask=True)
            
            
            # Move to the inputs to GPU for forward pass
            inputs = {k: (v.to(self.device) if isinstance(v, torch.Tensor) else v) for k, v in inputs.items()}
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.model(**inputs) 
                # The output is a tuple. Here we pass the inputs through the model to generate embeddings.
                hidden_states = outputs[0] # [1, seq_len, 768] eg. [1,512,768]
                
                # Mean pooling across tokens
                embedding = hidden_states.mean(dim=1).squeeze().cpu().numpy()
                window_embeddings.append(embedding)

        # Get the mean across all the windows such that we have one single embedding for the entire long sequence
        window_embeddings = np.array(window_embeddings)
        final_embeddings = window_embeddings.mean(axis=0)
        
        return final_embeddings
                

if __name__ == "__main__":

    # Initialize embedder
    embedder = DNABERTSContigEmbedder(device="cuda")
    
    #embedding = embedder.embed_contigs(fasta_file="/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/06_assembly/zr23059_100/final.contigs.fa")
    #print(embedding)

    test_seq = "ATCGATCGATCGATTTTATGGGTCGATCG" * 5  # 1000bp test sequence
    embedding = embedder.embed_sequence(test_seq)
    print(f"Sequence length: {len(test_seq)} bp")
    #print(f"Embedding shape: {embedding.shape}")
    #print(f"Embedding (first 10 dims): {embedding[:10]}")

    #embedding = embedder.embed_contigs(fasta_file="/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/06_assembly/zr23059_100/final.contigs.fa")
    #print(f"{embedding}")


"""

awk '/^>/ { if (NR>1) print len; len=0; next } { len +=length($0) } END { if (NR>0) print len }' final.contigs.fa | sort -n | uniq | wc -l
2790

"""