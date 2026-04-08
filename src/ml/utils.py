# Importing libraries
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import umap

from ml.data_loading import DatabaseRSA, db_reader


def plot_umap_by_zone(
    df: pd.DataFrame,
    label_col: str = "zone",
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    random_state: int = 42,
    title: str = "UMAP by Zone",
    save_path: str = "umap_plot.png",
):
    """
    Plots a UMAP projection of the feature columns, colored by the label_col (zone).
    """
    feature_cols = [col for col in df.columns if col not in ["sample_id", "latitude", "longitude", "zone"]]
    features = df[feature_cols].values
    labels = df[label_col].values

    reducer = umap.UMAP(n_neighbors=n_neighbors, min_dist=min_dist, random_state=random_state)
    embedding = reducer.fit_transform(features)

    plt.figure(figsize=(8, 7))
    sns.scatterplot(x=embedding[:, 0], y=embedding[:, 1], hue=labels, palette="tab10", s=30, alpha=0.8, linewidth=0)
    plt.title(title)
    plt.xlabel("UMAP1")
    plt.ylabel("UMAP2")
    plt.legend(title=label_col, bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()


def plot_barplot_by_zone(df: pd.DataFrame, save_path: str = "stacked_barplot.png"):
    """
    Plot stacked barplot with for each zone.
    """
    # Filter dataframe
    df = df.drop(["sample_id", "latitude", "longitude"], axis=1)
    # Convert everything except zone to float
    df = df.astype({col: "float" for col in df.columns if col != "zone"})
    zone_df = df.groupby(by="zone").mean()

    zone_df = zone_df.loc[:, (zone_df >= 0.005).any(axis=0)]

    # Plot stacked bar plot
    # set the figure size
    plt.figure(figsize=(14, 14))
    zone_df.iloc[:, :10].plot(kind="bar", stacked=True, figsize=(14, 8))
    plt.title("RSA Values by Zone and Phylum")
    plt.xlabel("Zone")
    plt.ylabel("RSA Value")
    plt.legend(title="Phylum", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()

    return zone_df


samples = db_reader.DatabaseCreate(db="../../databases/malmo.db")
rsa = DatabaseRSA(db="../../databases/malmo.db", db_table="malmo_species")
df = rsa.merge_data(samples.get_samples(), rsa.sql_to_clean())

# plot_umap_by_zone(df)

zone_df = plot_barplot_by_zone(df)
print(zone_df)
