# Get the latittude and longitude from the database
import sqlite3 
import numpy as np
import pandas as pd
import os
import geopandas as gpd
import folium
from folium import plugins
import osmnx as ox
import matplotlib.pyplot as plt
import json
from db_reader import DatabaseCreate


ZONE_COLORS = {
    "Zone A - Centrum":   "#e74c3c",   # Red
    "Zone B - Husie":     "#3498db",   # Blue
    "Zone C - Limhamn":   "#2ecc71",   # Light Green
    "Zone D - Rosengard": "#f39c12",   # Orange
    "Zone E - Hyllie":    "#9b59b6",   # Purple
    "Zone F - Kirseberg": "#1abc9c",   # Light Blue
    "Zone G - Oxie":      "#e67e22",   # Dark Orange
    "Zone H - Fosie":     "#e91e8c",   # Pink
}

DEFAULT_COLOR = "#95a5a6"


def get_zone_color(zone_name):
    for key in ZONE_COLORS:
        if key in str(zone_name):
            return ZONE_COLORS[key]
    return DEFAULT_COLOR


def load_malmo_boundary():
    """
    Downloads the Malmo admistrative boundary using OSMnx
    Return a GeoDataFrame.
    """
    print("Fetching the Malmo boundary from OpenStreetMap")
    city_name = "Malmö, Sweden"
    admin = ox.geocode_to_gdf(city_name)
    print(f"Boundary loaded: {admin.name[0]}")

    return admin


def boundary_to_geojson(admin_gdf):
    """
    Converts the OSMnx GeoDataFrame boundary to GeoJSON string so Folum can render it.
    """
    admin_wgs = admin_gdf.to_crs(epsg=4326)
    return json.loads(admin_wgs.to_json())


def build_malmo_map(df, admin_gdf, output_file = "malmo_interactive_map.html"):
    """
    Builds a full interactive Folium map:
    - OSMnx Malmo boundary 
    - Sample points colored by zone
    - Click popups with metadata
    - Hover tooltips
    - Heatmap layer
    - Marker cluster layer
    - Layer switcher
    - Minimap, fullscreen, measure tool
    """

    MALMO_CENTER = [55.6050, 13.0038]

    # Base Map
    m = folium.Map(
        location=MALMO_CENTER,
        zoom_start=12,
        tiles=None,
        control_scale=True
    )

    # Tile layers
    folium.TileLayer(
        "OpenStreetMap",
        name="OpenStreetMap",
        show=True
    ).add_to(m)

    folium.TileLayer(
        "CartoDB positron",
        name="Light (CartoDB)",
        show=False
    ).add_to(m)

    folium.TileLayer(
        "CartoDB dark_matter",
        name="Dark (CartoDB)",
        show=False
    ).add_to(m)


    # Malmo boundary polygon
    boundary_geojson = boundary_to_geojson(admin_gdf)

    boundary_layer = folium.FeatureGroup(name="Malmo Boundary", show=True)
    folium.GeoJson(
        boundary_geojson,
        name="Malmo Boundary",
        style_function=lambda _: {
            "fillColor":   "#4a9eff",
            "color":       "#1a5fa8",
            "weight":       2.5,
            "fillOpacity":  0.08,
            "dashArray":   "6 4"
        },
        tooltip="Malmo, Sweden"
    ).add_to(boundary_layer)
    boundary_layer.add_to(m)

    # Individual sample markers
    sample_layer = folium.FeatureGroup(name="Sample points", show=True)

    for _, row in df.iterrows():
        color = get_zone_color(row.get("zone",""))

        # Popup HTML 
        popup_html = f"""
        <div style="
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px;
            width: 240px;
            border-radius: 8px;
            overflow: hidden;
        ">
            <!-- Header -->
            <div style="
                background: {color};
                color: white;
                padding: 10px 12px;
                font-size: 14px;
                font-weight: bold;
            ">
                {row['sample_id']}
            </div>

            <!-- Body -->
            <div style="padding: 10px 12px; background: #f8f9fa;">
                <table style="width:100%; border-collapse:collapse; font-size:12px;">
                    <tr style="border-bottom:1px solid #eee;">
                        <td style="padding:4px; color:#666; width:45%;">Barcode</td>
                        <td style="padding:4px; font-weight:bold;">{row['barcode']}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee;">
                        <td style="padding:4px; color:#666;">Collector</td>
                        <td style="padding:4px;">{row['name']}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee;">
                        <td style="padding:4px; color:#666;">Latitude</td>
                        <td style="padding:4px;">{row['latitude']:.5f}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee;">
                        <td style="padding:4px; color:#666;">Longitude</td>
                        <td style="padding:4px;">{row['longitude']:.5f}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee;">
                        <td style="padding:4px; color:#666;">Precision</td>
                        <td style="padding:4px;">{row.get('precision','N/A')} m</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee;">
                        <td style="padding:4px; color:#666;">Date</td>
                        <td style="padding:4px;">{row.get('collection_date','N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding:4px; color:#666;">Zone</td>
                        <td style="padding:4px;">
                            <span style="
                                background:{color};
                                color:white;
                                padding:2px 6px;
                                border-radius:10px;
                                font-size:10px;
                            ">{row.get('zone','N/A')}</span>
                        </td>
                    </tr>
                </table>
            </div>
        </div>
        """

        # Tooltip (hover)
        tooltip_html = (
            f"<b>{row['sample_id']}</b> | "
            f"{row.get('zone','')}<br>"
            f"Lat: {row['latitude']:.4f}, Lon: {row['longitude']:.4f}"
        )

        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=9,
            color="white",
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=folium.Tooltip(tooltip_html, sticky=False)
        ).add_to(sample_layer)

    sample_layer.add_to(m)

    # Heatmap Layer
    heat_layer = folium.FeatureGroup(name="Sample Density Heatmap", show=False)
    heat_data  = [[row["latitude"], row["longitude"]] for _, row in df.iterrows()]
    plugins.HeatMap(
        heat_data,
        radius=30,
        blur=20,
        min_opacity=0.3,
        max_zoom=14,
        gradient={
            0.2: "#313695",
            0.4: "#74add1",
            0.6: "#fee090",
            0.8: "#f46d43",
            1.0: "#a50026"
        }
    ).add_to(heat_layer)
    heat_layer.add_to(m)

    # Marker cluster layer 
    cluster_layer = folium.FeatureGroup(name="Clustered Markers", show=False)
    marker_cluster = plugins.MarkerCluster(
        options={
            "maxClusterRadius": 40,
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": True
        }
    )
    for _, row in df.iterrows():
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            icon=folium.Icon(
                color="blue",
                icon="flask",
                prefix="fa"
            ),
            tooltip=f"{row['sample_id']} | {row.get('zone','')}",
            popup=folium.Popup(f"<b>{row['sample_id']}</b>", max_width=150)
        ).add_to(marker_cluster)
    marker_cluster.add_to(cluster_layer)
    cluster_layer.add_to(m)

    # Zone legend HTML 
    legend_items = ""
    unique_zones = df["zone"].unique() if "zone" in df.columns else []
    for zone in unique_zones:
        col = get_zone_color(zone)
        legend_items += f"""
        <div style="display:flex; align-items:center; margin-bottom:5px;">
            <div style="
                width:14px; height:14px;
                background:{col};
                border-radius:50%;
                margin-right:8px;
                border:1px solid #fff;
                flex-shrink:0;
            "></div>
            <span style="font-size:11px;">{zone}</span>
        </div>
        """

    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 40px;
        right: 10px;
        z-index: 1000;
        background: rgba(255,255,255,0.95);
        border: 1px solid #ccc;
        border-radius: 10px;
        padding: 12px 16px;
        font-family: 'Segoe UI', Arial, sans-serif;
        box-shadow: 0 2px 10px rgba(0,0,0,0.15);
        max-width: 200px;
    ">
        <div style="font-weight:bold; font-size:13px; margin-bottom:8px; 
                    border-bottom:1px solid #eee; padding-bottom:6px;">
            Collection Zones
        </div>
        {legend_items}
        <div style="margin-top:10px; padding-top:6px; 
                    border-top:1px solid #eee; font-size:10px; color:#666;">
            Total samples: <b>{len(df)}</b>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Title bar HTML 
    title_html = """
    <div style="
        position: fixed;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 1000;
        background: rgba(255,255,255,0.95);
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 8px 20px;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 15px;
        font-weight: bold;
        color: #2c3e50;
        box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        pointer-events: none;
    ">
        Microdentify — Malmö Sample Collection Map
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # UI Plugins
    plugins.Fullscreen(
        position="topright",
        title="Fullscreen",
        title_cancel="Exit Fullscreen"
    ).add_to(m)

    plugins.MiniMap(
        tile_layer="CartoDB positron",
        position="bottomleft",
        toggle_display=True,
        minimized=False,
        width=160,
        height=120
    ).add_to(m)

    plugins.MousePosition(
        position="bottomright",
        separator=" | ",
        prefix="*",
        num_digits=5
    ).add_to(m)

    plugins.MeasureControl(
        position="topleft",
        primary_length_unit="meters",
        secondary_length_unit="kilometers",
        primary_area_unit="sqmeters"
    ).add_to(m)

    plugins.Draw(
        export=True,
        position="topleft",
        draw_options={
            "polyline":  True,
            "rectangle": True,
            "circle":    True,
            "polygon":   True,
            "marker":    True
        }
    ).add_to(m)

    # Layer control 
    folium.LayerControl(
        position="topright",
        collapsed=False
    ).add_to(m)

    # Save
    m.save(output_file)
    print(f"Map saved to: {output_file}")
    print(f"Samples plotted: {len(df)}")
    print(f"Zones: {df['zone'].nunique() if 'zone' in df.columns else 'N/A'}")
    return m


if __name__ == "__main__":
    # 1. Load sample data (swap with your real DB function)
    print("Loading sample locations...")
    df = DatabaseCreate(db="./databases/malmo.db").get_samples()
    print(f"{len(df)} samples loaded")

    # 2. Load Malmo boundary via OSMnx
    admin = load_malmo_boundary()

    # 3. Build the interactive map
    print("\nBuilding interactive map...")
    build_malmo_map(df, admin, output_file="malmo_interactive_map.html")