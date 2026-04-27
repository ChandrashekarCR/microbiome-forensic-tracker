"""Interactive Malmo sample collection map generator."""

from malmo_samples.db_reader import DatabaseCreate
from malmo_samples.map_builder import build_malmo_map, load_malmo_boundary


def main():
    """Main execution function."""
    # Load sample data
    print("Loading sample locations...")
    df = DatabaseCreate(db="./databases/malmo.db").get_samples()
    print(f"{len(df)} samples loaded\n")
    print(df.head())

    # Load Malmo boundary
    admin = load_malmo_boundary()

    # Build interactive map
    print("\nBuilding interactive map...")
    build_malmo_map(df, admin, output_file="malmo_interactive_map.html")


if __name__ == "__main__":
    main()
