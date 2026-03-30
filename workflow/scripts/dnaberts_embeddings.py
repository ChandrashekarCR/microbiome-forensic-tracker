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
            inputs = self.tokenizer(window, return_tensors="pt", truncation=True,
                                    max_length=max_length, padding='longest', return_attention_mask=True)
            
            
            # Move to the inputs to GPU for forward pass
            inputs = {k: (v.to(self.device) if isinstance(v, torch.Tensor) else v) for k, v in inputs.items()}
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.model(**inputs) 
                # The output is a tuple. Here we pass the inputs through the model to generate embeddings.
                hidden_states = outputs[0] # [1, seq_len, 768] eg. [1,512,768]
                
                # Mean pooling across tokens
                embedding = hidden_states.mean(dim=1).cpu().numpy()
                window_embeddings.append(embedding[0])

        # Get the mean across all the windows such that we have one single embedding for the entire long sequence
        window_embeddings = np.array(window_embeddings)
        final_embeddings = window_embeddings.mean(axis=0)
        
        return final_embeddings
    
    def embed_contigs(self, fasta_file, output_file=None, batch_size=64, max_length=512, overlap=0.5):
        """
        Generate embeddings for all contigs in a FASTA file.
        
        Args:
            fasta_file: Path to FASTA file
            output_file: Optional path to save embeddings as JSON
            batch_size: Batch size for processing
            max_length: Maximum sequence length (tokens)
            overlap: Overlap ratio for windowing (0.5 = 50%)
        """
        print(f"Processing contigs from: {fasta_file}")

        # Load contigs
        contigs = []
        contig_ids = []
        contig_lengths = []

        for record in SeqIO.parse(fasta_file, "fasta"):
            seq = str(record.seq).upper()
            contigs.append(seq)
            contig_ids.append(record.id)
            contig_lengths.append(len(seq))

        print(f"Number of contigs are {len(contigs)}")
        print(f"Length range: {min(contig_lengths)}-{max(contig_lengths)} bp")

        # Generate embeddings
        # Tokenize -> Window function for longer sequences -> Embed

        all_embeddings = []

        for i in tqdm(range(0,len(contigs), batch_size), desc="Embedding contigs"):
            batch_seqs = contigs[i:i+batch_size]
            batch_ids = contig_ids[i:i+batch_size]
            
            batch_embeddings = []

            # Process each sequence in batch 
            for seq, contig_id in zip(batch_seqs, batch_ids):
                embedding = self.embed_sequence(sequence=seq, max_length=max_length, overlap=overlap)
                batch_embeddings.append(embedding)
            
            all_embeddings.extend(batch_embeddings)
        
        # Convert to numpy
        all_embeddings = np.array(all_embeddings)
        print(all_embeddings, all_embeddings.shape)

        # Save embeddings if output file is specified
        if output_file:
            embedding_dict = {
                "contigs_ids": contig_ids,
                "embeddings": all_embeddings.tolist(),
                "embedding_dim": all_embeddings.shape[1]
            }

            with open(output_file,"w") as f:
                json.dump(embedding_dict, f)
            
            print(f"Embedding saved to {output_file}")
        
        return all_embeddings, contig_ids


if __name__ == "__main__":

    # Initialize embedder
    embedder = DNABERTSContigEmbedder(device="cuda")
    
    #embedding = embedder.embed_contigs(fasta_file="/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/06_assembly/zr23059_100/final.contigs.fa")
    #print(embedding)

    #test_seq = "ATCGATCGATCGATTTTATGGGTCGATCG" * 50  # 1000bp test sequence
    #embedding = embedder.embed_sequence(test_seq)
    #print(f"Sequence length: {len(test_seq)} bp")
    #print(f"Embedding shape: {embedding.shape}")
    #print(f"Embedding (first 10 dims): {embedding[:10]}")

    embeddings = embedder.embed_contigs(fasta_file="/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/06_assembly/zr23059_100/final.contigs.fa",
                                       output_file="embedding.json",
                                       max_length=512,
                                       batch_size=128,
                                       overlap=0.3)
    print(f"Generated {len(embeddings)} embeddings")
    print(f"Embedding shape: {embeddings.shape}")
    #print(f"{embeddings}")


"""

awk '/^>/ { if (NR>1) print len; len=0; next } { len +=length($0) } END { if (NR>0) print len }' final.contigs.fa | sort -n | uniq | wc -l
2790

"""