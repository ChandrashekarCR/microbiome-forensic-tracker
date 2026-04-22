"""Main map building logic for Malmo sample visualization."""

import folium
import osmnx as ox
from malmo_samples.map_components import (
    add_base_layers,
    add_boundary_layer,
    add_cluster_layer,
    add_heatmap_layer,
    add_legend,
    add_sample_layer,
    add_title,
    add_ui_plugins,
)

from config import MALMO_CENTER


def load_malmo_boundary():
    """Download Malmo administrative boundary using OSMnx."""
    print("Fetching the Malmo boundary from OpenStreetMap")
    city_name = "Malmö, Sweden"
    admin = ox.geocode_to_gdf(city_name)
    print(f"Boundary loaded: {admin.name[0]}")
    return admin


def build_malmo_map(df, admin_gdf, output_file="malmo_interactive_map.html"):
    """
    Build a full interactive Folium map with all layers and controls.

    Args:
        df: DataFrame with sample data
        admin_gdf: GeoDataFrame with Malmo boundary
        output_file: Output HTML file path

    Returns:
        folium.Map object
    """
    # Initialize base map
    m = folium.Map(location=MALMO_CENTER, zoom_start=12, tiles=None, control_scale=True)

    # Add all components
    add_base_layers(m)
    add_boundary_layer(m, admin_gdf)
    add_sample_layer(m, df)
    add_heatmap_layer(m, df)
    add_cluster_layer(m, df)
    add_legend(m, df)
    add_title(m)
    add_ui_plugins(m)

    # Save map
    m.save(output_file)

    print(f"\n{'=' * 50}")
    print(f"Map saved to: {output_file}")
    print(f"Samples plotted: {len(df)}")
    print(f"Zones: {df['zone'].nunique() if 'zone' in df.columns else 'N/A'}")
    print(f"{'=' * 50}\n")

    return m
