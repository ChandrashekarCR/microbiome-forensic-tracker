# Map components for visulization
import folium
from folium import plugins
import json
from pathlib import Path
from jinja2 import Template
from config import ZONE_COLORS, DEFAULT_COLOR, BOUNDARY_STYLE, HEATMAP_GRADIENT

def get_zone_color(zone_name):
    """Get color for a given zone."""
    for key in ZONE_COLORS:
        if key in str(zone_name):
            return ZONE_COLORS[key]
    return DEFAULT_COLOR


def load_template(template_name):
    """Load HTML template from templates directory."""
    template_path = Path(__file__).parent / "templates" / template_name
    with open(template_path, 'r') as f:
        return Template(f.read())


def add_base_layers(map_obj):
    """Add base tile layers to the map."""
    folium.TileLayer(
        "OpenStreetMap",
        name="OpenStreetMap",
        show=True
    ).add_to(map_obj)

    folium.TileLayer(
        "CartoDB positron",
        name="Light (CartoDB)",
        show=False
    ).add_to(map_obj)

    folium.TileLayer(
        "CartoDB dark_matter",
        name="Dark (CartoDB)",
        show=False
    ).add_to(map_obj)


def add_boundary_layer(map_obj, admin_gdf):
    """Add Malmo boundary polygon to the map."""
    admin_wgs = admin_gdf.to_crs(epsg=4326)
    boundary_geojson = json.loads(admin_wgs.to_json())

    boundary_layer = folium.FeatureGroup(name="Malmo Boundary", show=True)
    folium.GeoJson(
        boundary_geojson,
        name="Malmo Boundary",
        style_function=lambda _: BOUNDARY_STYLE,
        tooltip="Malmo, Sweden"
    ).add_to(boundary_layer)
    boundary_layer.add_to(map_obj)


def create_sample_marker(row, template):
    """Create a single sample marker with popup and tooltip."""
    color = get_zone_color(row.get("zone", ""))
    
    # Render popup from template
    popup_html = template.render(
        sample_id=row['sample_id'],
        barcode=row['barcode'],
        name=row['name'],
        latitude=row['latitude'],
        longitude=row['longitude'],
        precision=row.get('precision', 'N/A'),
        date=row['date'],
        time = row['time'],
        zone=row.get('zone', 'N/A'),
        color=color
    )
    
    tooltip_html = (
        f"<b>{row['sample_id']}</b> | "
        f"{row.get('zone','')}<br>"
        f"Lat: {row['latitude']:.4f}, Lon: {row['longitude']:.4f}"
    )
    
    return folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=9,
        color="white",
        weight=1.5,
        fill=True,
        fill_color=color,
        fill_opacity=0.85,
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=folium.Tooltip(tooltip_html, sticky=False)
    )


def add_sample_layer(map_obj, df):
    """Add individual sample markers to the map."""
    sample_layer = folium.FeatureGroup(name="Sample points", show=True)
    popup_template = load_template("popup.html")
    
    for _, row in df.iterrows():
        marker = create_sample_marker(row, popup_template)
        marker.add_to(sample_layer)
    
    sample_layer.add_to(map_obj)


def add_heatmap_layer(map_obj, df):
    """Add heatmap layer to the map."""
    heat_layer = folium.FeatureGroup(name="Sample Density Heatmap", show=False)
    heat_data = [[row["latitude"], row["longitude"]] for _, row in df.iterrows()]
    
    plugins.HeatMap(
        heat_data,
        radius=30,
        blur=20,
        min_opacity=0.3,
        max_zoom=14,
        gradient=HEATMAP_GRADIENT
    ).add_to(heat_layer)
    
    heat_layer.add_to(map_obj)


def add_cluster_layer(map_obj, df):
    """Add marker cluster layer to the map."""
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
            icon=folium.Icon(color="blue", icon="flask", prefix="fa"),
            tooltip=f"{row['sample_id']} | {row.get('zone','')}",
            popup=folium.Popup(f"<b>{row['sample_id']}</b>", max_width=150)
        ).add_to(marker_cluster)
    
    marker_cluster.add_to(cluster_layer)
    cluster_layer.add_to(map_obj)


def add_legend(map_obj, df):
    """Add zone legend to the map."""
    legend_template = load_template("legend.html")
    
    zones = []
    unique_zones = df["zone"].unique() if "zone" in df.columns else []
    for zone in unique_zones:
        zones.append({
            "name": zone,
            "color": get_zone_color(zone)
        })
    
    legend_html = legend_template.render(
        zones=zones,
        total_samples=len(df)
    )
    
    map_obj.get_root().html.add_child(folium.Element(legend_html))


def add_title(map_obj):
    """Add title bar to the map."""
    title_template = load_template("title.html")
    title_html = title_template.render()
    map_obj.get_root().html.add_child(folium.Element(title_html))


def add_ui_plugins(map_obj):
    """Add UI plugins to the map."""
    plugins.Fullscreen(
        position="topright",
        title="Fullscreen",
        title_cancel="Exit Fullscreen"
    ).add_to(map_obj)

    plugins.MousePosition(
        position="bottomright",
        separator=" | ",
        prefix="*",
        num_digits=5
    ).add_to(map_obj)

    plugins.MeasureControl(
        position="topleft",
        primary_length_unit="meters",
        secondary_length_unit="kilometers",
        primary_area_unit="sqmeters"
    ).add_to(map_obj)

    plugins.Draw(
        export=True,
        position="topleft",
        draw_options={
            "polyline": True,
            "rectangle": True,
            "circle": True,
            "polygon": True,
            "marker": True
        }
    ).add_to(map_obj)

    folium.LayerControl(
        position="topright",
        collapsed=False
    ).add_to(map_obj)