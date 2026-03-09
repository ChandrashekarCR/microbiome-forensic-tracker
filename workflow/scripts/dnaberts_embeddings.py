import os
import sys
import torch
import pandas as pd
from Bio import SeqIO
from transformers import pipeline
from transformers import AutoTokenizer, AutoModel
from pathlib import Path
import json
from tqdm import tqdm


class DNABERTSContigEmbedder:
    """
    Generate DNABERT=S embedding for metagenomic assembled contigs.
    """

    def __init__(self,model_name="zhihan1996/DNABERT-S", device="cuda"):
        # Resolve device: use cuda only if available
        if device == "cuda":
            dev_str = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            dev_str = device
        self.device = torch.device(dev_str)
        print(f"Loading DNABERT-S on {self.device}...")

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained("zhihan1996/DNABERT-S", trust_remote_code=True)

        # Load the model and move to device
        self.model = AutoModel.from_pretrained("zhihan1996/DNABERT-S", trust_remote_code=True)
        self.model.to(self.device)

        # Set to evaluation mode
        self.model.eval()

        print(f"Model loaded successfully")
        print(f"Model has {sum(p.numel() for p in self.model.parameters()):,} parameters.")


    def embed_sequence(self, sequence, return_token_embeddings=False):
        """
        Generate embedding for a single DNA sequences
        """

        # Ensure the sequence are in upper case
        sequence = sequence.upper()

        # Tokenize
        # DNABERT-S max length is 512 tokens
        inputs = self.tokenizer(
            sequence,
            return_tensors='pt',
            truncation = True,   # Truncate if  > 512 tokens
            max_length = 512,
            padding = False,
            return_attention_mask = True
        )

        # Move tensor inputs to the model device (only move tensors)
        inputs = {k: (v.to(self.device) if isinstance(v, torch.Tensor) else v)
                  for k, v in inputs.items()}
        
        print(inputs)
        

        # Generate embeddings
        with torch.no_grad():
            outputs = self.model(**inputs)


            # Output last hidden state shape [1. num_tokens, 768]
            hidden_states = outputs.last_hidden_state

            if return_token_embeddings:
                return hidden_states[0].cpu().numpy()
            
            # Mean pooling across all tokens
            embedding = hidden_states.mean(dim=1).squeeze().cpu().numpy()

        return embedding




if __name__ == "__main__":

    # Initialize embedder
    embedder = DNABERTSContigEmbedder(device="cuda")

    test_seq = "ATCGATCGATCGATCGATCG" * 50  # 1000bp test sequence
    embedding = embedder.embed_sequence(test_seq)
    print(f"Sequence length: {len(test_seq)} bp")
    print(f"Embedding shape: {embedding.shape}")
    print(f"Embedding (first 10 dims): {embedding[:10]}")