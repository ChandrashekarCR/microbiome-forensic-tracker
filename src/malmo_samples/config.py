"""Configuration and constants for Malmo sample visualization."""

ZONE_COLORS = {
    "Zone A - Centrum": "#e74c3c",  # Red
    "Zone B - Husie": "#3498db",  # Blue
    "Zone C - Limhamn": "#2ecc71",  # Light Green
    "Zone D - Rosengard": "#f39c12",  # Orange
    "Zone E - Hyllie": "#9b59b6",  # Purple
    "Zone F - Kirseberg": "#1abc9c",  # Light Blue
    "Zone G - Oxie": "#e67e22",  # Dark Orange
    "Zone H - Fosie": "#e91e8c",  # Pink
}

DEFAULT_COLOR = "#95a5a6"
MALMO_CENTER = [55.6050, 13.0038]

# Heatmap gradient
HEATMAP_GRADIENT = {
    0.2: "#313695",
    0.4: "#74add1",
    0.6: "#fee090",
    0.8: "#f46d43",
    1.0: "#a50026",
}

# Boundary style
BOUNDARY_STYLE = {
    "fillColor": "#4a9eff",
    "color": "#07182b",
    "weight": 2.5,
    "fillOpacity": 0.08,
    "dashArray": "6 4",
}
