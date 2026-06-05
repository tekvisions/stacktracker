#!/usr/bin/env python3
"""Shared charting module for the Kymata Labs Instrument Family.

Generates SVG charts with consistent styling, accessibility, and responsive design.
Used by every tool's gen_details.py. Copy-pasteable reference implementation.

Key features:
- SVG-based, scales perfectly on any device
- Theme-aware (dark/light)
- Full ARIA labels for screen readers
- Consistent styling matching design system tokens
- No external dependencies
"""

from typing import List, Dict, Any, Optional, Tuple
import math


def line_chart(
    data: List[Dict[str, Any]],
    x_key: str,
    y_key: str,
    title: str,
    width: int = 800,
    height: int = 400,
    fill_area: bool = True,
    inverted_y: bool = False,
    accent: str = "var(--accent)"
) -> str:
    """Generate a responsive SVG line chart with area fill and data points.

    Args:
        data: List of data points with x and y values
        x_key: Key for x-axis values (should be dates or numeric)
        y_key: Key for y-axis values (numeric)
        title: Chart title for accessibility
        width: SVG viewBox width
        height: SVG viewBox height
        fill_area: Whether to fill area under the line
        inverted_y: Whether to invert y-axis (useful for rankings)
        accent: CSS color variable for the line/fill

    Returns:
        Complete SVG string with responsive styling
    """
    if not data:
        return f'<svg viewBox="0 0 {width} {height}"><text x="50%" y="50%" text-anchor="middle" fill="var(--ink-muted)">No data</text></svg>'

    # Chart dimensions with padding
    padding = 60
    chart_width = width - (padding * 2)
    chart_height = height - (padding * 2)

    # Extract and process data
    points = []
    for i, point in enumerate(data):
        if x_key in point and y_key in point:
            x_val = point[x_key]
            y_val = point[y_key]

            # Handle different x-axis types
            if isinstance(x_val, str):
                # Assume it's a date string - use index for spacing
                x_pos = i
            else:
                x_pos = x_val

            points.append((x_pos, y_val))

    if not points:
        return f'<svg viewBox="0 0 {width} {height}"><text x="50%" y="50%" text-anchor="middle" fill="var(--ink-muted)">No valid data</text></svg>'

    # Find data ranges
    x_values = [p[0] for p in points]
    y_values = [p[1] for p in points]

    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)

    # Add some padding to y-range
    y_range = y_max - y_min
    if y_range == 0:
        y_range = 1
    y_padding = y_range * 0.1
    y_min -= y_padding
    y_max += y_padding

    # Scale points to chart area
    def scale_x(x: float) -> float:
        if x_max == x_min:
            return padding + chart_width / 2
        return padding + ((x - x_min) / (x_max - x_min)) * chart_width

    def scale_y(y: float) -> float:
        if y_max == y_min:
            return padding + chart_height / 2
        normalized = (y - y_min) / (y_max - y_min)
        if inverted_y:
            normalized = 1 - normalized
        return padding + normalized * chart_height

    scaled_points = [(scale_x(x), scale_y(y)) for x, y in points]

    # Generate path data
    path_data = f"M {scaled_points[0][0]},{scaled_points[0][1]}"
    for x, y in scaled_points[1:]:
        path_data += f" L {x},{y}"

    # Generate area fill path (if enabled)
    area_path = ""
    if fill_area:
        bottom_y = padding + chart_height if not inverted_y else padding
        area_path = path_data
        area_path += f" L {scaled_points[-1][0]},{bottom_y}"
        area_path += f" L {scaled_points[0][0]},{bottom_y} Z"

    # Generate grid lines
    grid_lines = []

    # Horizontal grid lines
    for i in range(5):
        y_pos = padding + (i * chart_height / 4)
        grid_lines.append(f'<line x1="{padding}" y1="{y_pos}" x2="{padding + chart_width}" y2="{y_pos}" stroke="var(--line)" stroke-width="1" opacity="0.3" />')

    # Vertical grid lines
    for i in range(6):
        x_pos = padding + (i * chart_width / 5)
        grid_lines.append(f'<line x1="{x_pos}" y1="{padding}" x2="{x_pos}" y2="{padding + chart_height}" stroke="var(--line)" stroke-width="1" opacity="0.2" />')

    # Generate axis labels
    axis_labels = []

    # Y-axis labels
    for i in range(5):
        y_pos = padding + (i * chart_height / 4)
        value = y_max - ((i / 4) * (y_max - y_min))
        if inverted_y:
            value = y_min + ((i / 4) * (y_max - y_min))

        # Format the value nicely
        if value >= 1000:
            label = f"{value/1000:.1f}k"
        elif value >= 100:
            label = f"{int(value)}"
        else:
            label = f"{value:.1f}"

        axis_labels.append(f'<text x="{padding - 10}" y="{y_pos + 4}" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink-muted)">{label}</text>')

    # Data point circles with values
    point_circles = []
    for i, (x, y) in enumerate(scaled_points):
        original_y = y_values[i]

        # Format value for display
        if original_y >= 1000:
            value_text = f"{original_y/1000:.1f}k"
        else:
            value_text = str(int(original_y))

        # Circle
        point_circles.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{accent}" stroke="var(--bg)" stroke-width="2" />')

        # Value label (above or below point based on position)
        label_y = y - 15 if y > height/2 else y + 20
        point_circles.append(f'<text x="{x}" y="{label_y}" text-anchor="middle" font-family="var(--mono)" font-size="10" fill="var(--accent)" font-weight="500">{value_text}</text>')

    # Comprehensive ARIA label
    data_summary = f"{len(points)} data points"
    if points:
        first_val = y_values[0]
        last_val = y_values[-1]
        min_val = min(y_values)
        max_val = max(y_values)

        trend = "increasing" if last_val > first_val else "decreasing" if last_val < first_val else "stable"
        data_summary += f", trending {trend} from {first_val} to {last_val}, range {min_val} to {max_val}"

    # Build complete SVG
    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-labelledby="chart-title" aria-describedby="chart-desc">',
        f'<title id="chart-title">{title}</title>',
        f'<desc id="chart-desc">{title}: {data_summary}</desc>',

        # Background
        f'<rect width="{width}" height="{height}" fill="var(--panel)" rx="12" />',

        # Grid
        '\n'.join(grid_lines),

        # Area fill
        f'<path d="{area_path}" fill="{accent}" fill-opacity="0.1" />' if fill_area and area_path else '',

        # Line
        f'<path d="{path_data}" fill="none" stroke="{accent}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />',

        # Axis labels
        '\n'.join(axis_labels),

        # Data points
        '\n'.join(point_circles),

        '</svg>'
    ]

    return '\n'.join(filter(None, svg_parts))


def sparkline(
    data: List[float],
    width: int = 60,
    height: int = 24,
    accent: str = "var(--accent)"
) -> str:
    """Generate a minimal SVG sparkline for table cells.

    Args:
        data: List of numeric values
        width: SVG width in pixels
        height: SVG height in pixels
        accent: CSS color variable

    Returns:
        Compact SVG sparkline
    """
    if not data or len(data) < 2:
        return f'<svg width="{width}" height="{height}"><line x1="0" y1="{height/2}" x2="{width}" y2="{height/2}" stroke="var(--line)" stroke-width="1" /></svg>'

    # Find range
    y_min, y_max = min(data), max(data)
    y_range = y_max - y_min

    if y_range == 0:
        # Flat line
        return f'<svg width="{width}" height="{height}"><line x1="0" y1="{height/2}" x2="{width}" y2="{height/2}" stroke="{accent}" stroke-width="1.5" /></svg>'

    # Scale points
    points = []
    for i, value in enumerate(data):
        x = (i / (len(data) - 1)) * width
        y = height - ((value - y_min) / y_range) * height
        points.append((x, y))

    # Generate path
    path_data = f"M {points[0][0]},{points[0][1]}"
    for x, y in points[1:]:
        path_data += f" L {x},{y}"

    return f'''<svg width="{width}" height="{height}" class="board-sparkline">
<path d="{path_data}" fill="none" stroke="{accent}" stroke-width="1.5" stroke-linejoin="round" />
</svg>'''


def progress_bar(
    value: float,
    max_value: float = 100,
    width: int = 200,
    height: int = 6,
    accent: str = "var(--accent)"
) -> str:
    """Generate a progress bar SVG.

    Args:
        value: Current value
        max_value: Maximum value (100 for percentage)
        width: Bar width in pixels
        height: Bar height in pixels
        accent: CSS color variable

    Returns:
        SVG progress bar
    """
    percentage = min(100, max(0, (value / max_value) * 100))
    fill_width = (percentage / 100) * width

    return f'''<svg width="{width}" height="{height}" class="progress-bar">
<rect width="{width}" height="{height}" fill="var(--line)" rx="{height/2}" />
<rect width="{fill_width}" height="{height}" fill="{accent}" rx="{height/2}" />
</svg>'''


def radar_chart(
    data: Dict[str, float],
    size: int = 200,
    accent: str = "var(--accent)"
) -> str:
    """Generate a radar/spider chart SVG.

    Args:
        data: Dictionary of label -> value (0-100)
        size: Chart size in pixels
        accent: CSS color variable

    Returns:
        SVG radar chart
    """
    if not data:
        return f'<svg width="{size}" height="{size}"><text x="50%" y="50%" text-anchor="middle" fill="var(--ink-muted)">No data</text></svg>'

    center = size / 2
    radius = center - 30

    labels = list(data.keys())
    values = list(data.values())
    num_points = len(labels)

    if num_points < 3:
        # Fall back to horizontal bars for too few points
        bars = []
        for i, (label, value) in enumerate(data.items()):
            y_pos = 30 + i * 40
            bar_width = (value / 100) * (size - 60)
            bars.append(f'<rect x="30" y="{y_pos}" width="{bar_width}" height="20" fill="{accent}" opacity="0.7" />')
            bars.append(f'<text x="35" y="{y_pos + 14}" font-family="var(--mono)" font-size="10" fill="var(--ink)">{label}</text>')

        return f'<svg width="{size}" height="{size}">{"".join(bars)}</svg>'

    # Generate radar chart
    angle_step = 2 * math.pi / num_points

    # Grid circles
    grid_circles = []
    for r in [0.2, 0.4, 0.6, 0.8, 1.0]:
        grid_radius = radius * r
        grid_circles.append(f'<circle cx="{center}" cy="{center}" r="{grid_radius}" fill="none" stroke="var(--line)" stroke-width="1" opacity="0.3" />')

    # Axis lines
    axis_lines = []
    for i in range(num_points):
        angle = i * angle_step - math.pi / 2  # Start from top
        end_x = center + radius * math.cos(angle)
        end_y = center + radius * math.sin(angle)
        axis_lines.append(f'<line x1="{center}" y1="{center}" x2="{end_x}" y2="{end_y}" stroke="var(--line)" stroke-width="1" opacity="0.3" />')

    # Data polygon
    data_points = []
    for i, value in enumerate(values):
        angle = i * angle_step - math.pi / 2
        point_radius = radius * (value / 100)
        x = center + point_radius * math.cos(angle)
        y = center + point_radius * math.sin(angle)
        data_points.append((x, y))

    # Polygon path
    polygon_path = f"M {data_points[0][0]},{data_points[0][1]}"
    for x, y in data_points[1:]:
        polygon_path += f" L {x},{y}"
    polygon_path += " Z"

    # Labels
    label_elements = []
    for i, label in enumerate(labels):
        angle = i * angle_step - math.pi / 2
        label_radius = radius + 20
        x = center + label_radius * math.cos(angle)
        y = center + label_radius * math.sin(angle)

        # Adjust text anchor based on position
        text_anchor = "middle"
        if x < center - 5:
            text_anchor = "end"
        elif x > center + 5:
            text_anchor = "start"

        label_elements.append(f'<text x="{x}" y="{y + 4}" text-anchor="{text_anchor}" font-family="var(--mono)" font-size="10" fill="var(--ink-muted)">{label}</text>')

    return f'''<svg width="{size}" height="{size}" class="radar-chart">
{"".join(grid_circles)}
{"".join(axis_lines)}
<path d="{polygon_path}" fill="{accent}" fill-opacity="0.1" stroke="{accent}" stroke-width="2" />
{"".join(label_elements)}
</svg>'''


# Utility function for the existing StackTracker charts
def commit_volume_chart(monthly_data: List[int], width: int = 600, height: int = 200) -> str:
    """Generate commit volume chart matching StackTracker's existing pattern."""
    if not monthly_data:
        return ""

    # Convert to the format expected by line_chart
    data_points = []
    months = ["6mo", "5mo", "4mo", "3mo", "2mo", "1mo"]

    for i, count in enumerate(monthly_data):
        data_points.append({
            "month": months[i] if i < len(months) else f"{i}mo",
            "commits": count
        })

    return line_chart(
        data=data_points,
        x_key="month",
        y_key="commits",
        title="6-Month Commit Volume",
        width=width,
        height=height,
        fill_area=True,
        accent="var(--accent)"
    )


def rank_position_chart(history: List[Dict[str, Any]], width: int = 600, height: int = 200) -> str:
    """Generate rank position chart (inverted y-axis)."""
    if not history:
        return ""

    return line_chart(
        data=history,
        x_key="date",
        y_key="rank",
        title="Rank Position Over Time",
        width=width,
        height=height,
        fill_area=True,
        inverted_y=True,  # Lower rank numbers should be at the top
        accent="var(--accent)"
    )