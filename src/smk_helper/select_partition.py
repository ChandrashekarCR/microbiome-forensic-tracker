"""
GPU partition selector for Kraken2 jobs in Lunarc
Filles partitions in priority order based on the node capacity:
    aurora (4 nodes, 768 G) -> gpua40 (6 nodes, 512 G) -> gpua40i (6 nodes, 512G)

There is Associated Group Memory Limit for eacho Research group and hence we cannot assign more jobs.

After all the 16 slots are assigned, round-robin from the least used partition.

"""

# Dynamic partitioning of resources
_GPU_PARTITION_NODES = {
    "aurora": 4,  # ca19-ca22 nodes have 768 G
    "gpua40": 6,  # cg01-cg06 nodes have 512 G
    "gpua40i": 6,  # cg13-cg17, cg23 nodes have 512 G
}
GPU_PARTITION_PRIORITY = list(_GPU_PARTITION_NODES.keys())  # priority order

# Mutable counter - persists for the lifetime of the Snakemake process
_partition_dispatched = dict.fromkeys(GPU_PARTITION_PRIORITY, 0)


def select_best_partition(wildcards=None):
    """
    Distribute kraken jobs across GPU partitions by node capacity.

    Fills partitions in priority order:
      aurora (4) -> gpua40 (6) -> gpua40i (6)
    After all 16 slots are taken, round-robins from the least-used partition.
    """
    # Fill each partition up to its node capacity before moving on
    for partition in GPU_PARTITION_PRIORITY:
        capacity = _GPU_PARTITION_NODES[partition]
        if _partition_dispatched[partition] < capacity:
            _partition_dispatched[partition] += 1
            print(
                f"[partition selector] {partition} "
                f"({_partition_dispatched[partition]}/{capacity} slots used)"
            )
            return partition

    # All 16 slots filled (happens when >16 kraken jobs are ready at once).
    # Round-robin: pick whichever partition has the fewest dispatched jobs.
    least = min(_partition_dispatched, key=_partition_dispatched.get)
    _partition_dispatched[least] += 1
    print(f"[partition selector] All slots full - round-robin to {least}")
    return least


def reset_partition_counters():
    """Reset counters — useful for unit testing."""
    for p in GPU_PARTITION_PRIORITY:
        _partition_dispatched[p] = 0
