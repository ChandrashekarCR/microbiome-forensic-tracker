# Importing libraries
import argparse
import json

import numpy as np
import torch
from Bio import SeqIO
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

"""
To check the seqeunce length distribution
awk '/^>/ { if (NR>1) print len; len=0; next } { len +=length($0) } END { if (NR>0) print len }' final.contigs.fa | sort -n | uniq | wc -l
2790

"""

# DNABERT-S model name
MODEL_NAME = "zhihan1996/DNABERT-S"


class DNABERTSContigEmbedder:
    """
    Generate DNABERT=S embedding for metagenomic assembled contigs.
    """

    def __init__(self, model_name=MODEL_NAME, device="cuda"):
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

        print("Model loaded successfully")
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
        for start in range(0, len(sequence), stride):
            end = min(start + max_length, len(sequence))
            windows.append(sequence[start:end])

            # Stop if we have reached the end
            if end == len(sequence):
                break

        return windows

    def _masked_mean_pool(self, hidden_states, attention_mask):
        """
        Correct masked mean pooling excluding [CLS] and [SEP] tokens.

        Args:
            hidden_states: [batch_size, seq_len, 768]
            attention_mask: [batch_size, seq_len] (1=real token, 0=pad)

        Returns:
            [batch_size, 768] pooled embeddings
        """
        # Clone attention mask to build content mask
        content_mask = attention_mask.clone().float()

        # Zero out [CLS] at position 0
        content_mask[:, 0] = 0

        # Zero out [SEP] at last real position
        seq_lengths = attention_mask.sum(dim=1).long()
        for b in range(hidden_states.shape[0]):
            sep_pos = seq_lengths[b] - 1
            content_mask[b, sep_pos] = 0

        # Expand mask: [batch_size, seq_len] → [batch_size, seq_len, 768]
        mask_expanded = content_mask.unsqueeze(-1)  # [batch_size, seq_len, 1]

        # Sum embeddings of real tokens only
        sum_embeddings = (hidden_states * mask_expanded).sum(dim=1)  # [batch_size, 768]
        sum_mask = mask_expanded.sum(dim=1).clamp(min=1e-9)  # [batch_size, 768]

        return sum_embeddings / sum_mask  # [batch_size, 768]

    def embed_sequence_batch(self, sequences: list, max_length: int = 512, overlap: float = 0.5):
        """
        TRUE GPU-level batching: ALL sequences and their windows in ONE forward pass.

        Args:
            sequences: List of DNA sequence strings (e.g., 128 contigs)

        Returns:
            List of embeddings, one per input sequence (not per window)
        """
        # Step 1: Create windows for all sequences and track which sequence each window belongs to
        all_windows = []
        sequence_window_counts = []  # Track how many windows each sequence has
        for sequence in sequences:
            if len(sequence) <= max_length:
                windows = [sequence]
            else:
                windows = self.create_windows(sequence, max_length, overlap)

            all_windows.extend(windows)
            sequence_window_counts.append(len(windows))

        # Step 2: Tokenize ALL windows together (one giant batch)
        inputs = self.tokenizer(
            all_windows,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding="longest",
            return_attention_mask=True,
        )

        # Move to GPU
        inputs = {k: (v.to(self.device) if isinstance(v, torch.Tensor) else v) for k, v in inputs.items()}

        # Step 3: One forward pass for all windows at once
        with torch.no_grad():
            outputs = self.model(**inputs)
            hidden_states = outputs[0]  # [total_windows, seq_len, 768]

            # Use correct masked pooling
            all_window_embeddings = self._masked_mean_pool(hidden_states, inputs["attention_mask"]).cpu().numpy()  # [total_windows, 768]

        # Step 4: Group window embeddings back by original sequence and average
        sequence_embeddings = []
        start_idx = 0

        for num_windows in sequence_window_counts:
            end_idx = start_idx + num_windows
            windows_for_seq = all_window_embeddings[start_idx:end_idx]  # [num_windows, 768]
            sequence_embedding = windows_for_seq.mean(axis=0)  # [768]
            sequence_embeddings.append(sequence_embedding)
            start_idx = end_idx

        return sequence_embeddings

    def embed_contigs(self, fasta_file, output_file=None, batch_size=32, max_length=512, overlap=0.3):
        """
        Generate embeddings for all contigs in a FASTA file with GPU-level batching.

        Args:
            fasta_file: Path to FASTA file
            output_file: Optional path to save embeddings as JSON
            batch_size: Number of CONTIGS to process in each GPU batch
            max_length: Maximum sequence length (tokens)
            overlap: Overlap ratio for windowing (0.3 = 30%)
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

        print(f"Number of contigs: {len(contigs)}")
        print(f"Length range: {min(contig_lengths):,}-{max(contig_lengths):,} bp")

        # GPU-level batching: Process multiple contigs per forward pass
        all_embeddings = []

        for i in tqdm(range(0, len(contigs), batch_size), desc="Embedding contigs"):
            batch_seqs = contigs[i : i + batch_size]

            # This function will tokenize all sequences at once
            # and run one forward pass that processes all of them
            batch_embeddings = self.embed_sequence_batch(batch_seqs, max_length=max_length, overlap=overlap)

            all_embeddings.extend(batch_embeddings)

        # Convert to numpy
        all_embeddings = np.array(all_embeddings)
        print(f"Embeddings shape: {all_embeddings.shape}")

        # Save embeddings if output file is specified
        if output_file:
            embedding_dict = {
                "contig_ids": contig_ids,
                "embeddings": all_embeddings.tolist(),
                "embedding_dim": all_embeddings.shape[1],
            }

            with open(output_file, "w") as f:
                json.dump(embedding_dict, f)

            print(f"Embedding saved to {output_file}")

        return all_embeddings

    # def json_parse_embeddings(self,json_embed):
    #    with open(json_embed) as f:
    #        data = json.load(f)
    #    return


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="A script to generate DNABERT-S embeddings",
        usage="python3 dnaberts_embeddings.py -i <fasta_file> -o <json_file> \
                                        -b <batch_size> -m <max-length> -l <overlap> -d<device>",
    )
    parser.add_argument("-i", dest="fasta", required=True, help="Enter the fasta file.")
    parser.add_argument("-o", dest="output", required=True, help="Enter the output JSON file.")
    parser.add_argument("-b", dest="batch_size", type=int, default=128)
    parser.add_argument("-m", dest="max_length", type=int, default=512)
    parser.add_argument("-l", dest="overlap", type=float, default=0.5)
    parser.add_argument("-d", dest="device", default="cuda")

    args = parser.parse_args()

    # Initialize embedder
    embedder = DNABERTSContigEmbedder(device=args.device)

    embeddings = embedder.embed_contigs(
        fasta_file=args.fasta,
        output_file=args.output,
        max_length=args.max_length,
        batch_size=args.batch_size,
        overlap=args.overlap,
    )

    print(f"Successfully embedded {embeddings.shape[0]} to {args.output}")

    # embedder.json_parse_embeddings("embedding.json")

"""
Run the script as follows -:
python3 src/smk_helper/dnaberts_embeddings.py \
    -i /home/chandru/binp51/results/06_assembly/zr23059_170/zr23059_170.fa \
    -o zr23059_170_embeddings.json \
    -b 128 \
    -m 512 \
    -l 0.5 \
    -d cuda \
"""
