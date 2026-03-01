---
name: figdatax
description: "FigDataX: High-precision scientific figure data extraction via axis-calibrated semi-automatic methods. Extracts numerical data from paper figures (bar, line, scatter, box, heatmap, pie, polar, stacked charts) with sub-pixel precision. Core approach: multi-point axis calibration + color-based detection. Also supports fully-automated color segmentation and Hough-line-guided curve tracing. Features: automatic plot area detection, adaptive grid removal, multi-point least-squares axis calibration, sub-pixel Gaussian centroid refinement, contour-based curve tracing, and validation overlay. Use when the user wants to digitize a chart, extract data from a figure, get numbers from a graph, convert a plot to a data table. Also trigger on: '读取图中数据', '从图中提取数值', '图表数字化', '提取图表数据', 'plot digitizer', 'digitize figure', 'extract figure data', 'figure data extraction'."
---

# FigDataX — High-Precision Scientific Figure Data Extraction

**FigDataX** = **Fig**ure **Data** e**X**traction

Extract numerical data from scientific paper figures with up to ±0.5% accuracy, centered on multi-point axis-calibrated semi-automatic extraction.

## Setup & File Paths

### Python dependencies

```bash
pip3 install opencv-python numpy pandas matplotlib scipy openpyxl scikit-image
```

### Import path

The FigDataX Python library is located at `~/.claude/skills/figdatax/scripts/figdatax.py`. To import it from any working directory, add the skill root to `sys.path`:

```python
import sys
sys.path.insert(0, "/PATH/TO/.claude/skills/figdatax")  # adjust to actual path
from scripts.figdatax import calibrate_axes_multipoint, auto_detect_plot_area, ...
```

> **Note**: Replace `/PATH/TO/` with the actual absolute path to the user's `.claude/` directory. Use `os.path.expanduser("~/.claude/skills/figdatax")` to resolve `~` if needed.

### Working directory & output files

- **Input**: The user provides the image file path (absolute or relative to their current working directory).
- **Output**: All generated files (CSV, validation plot, grid overlay, etc.) are saved **in the same directory as the input image**, not the skill directory. Use `os.path.dirname(image_path)` to determine the output directory.
- **Naming convention**: Output files are named after the input image:
  - `{image_stem}_extracted.csv` — extracted data table
  - `{image_stem}_validation.png` — side-by-side validation plot
  - `{image_stem}_grid.png` — coordinate grid overlay (intermediate, for manual reading)

Example:
```
Input:  /Users/alice/papers/fig3.png
Output: /Users/alice/papers/fig3_extracted.csv
        /Users/alice/papers/fig3_validation.png
        /Users/alice/papers/fig3_grid.png
```

## Extraction Methods

| Method | Name | Best For | Typical Accuracy |
|--------|------|----------|-----------------|
| **M1** | **Calibrated Semi-Auto** | **All charts — the default and preferred method** | **±0.5-2%** |
| **M2** | Fully Automated | High-contrast charts with distinct colors | ±0.5-1% |
| **M3** | Hough + Curve Trace | Line charts, continuous curves | ±0.5-1% |

**Strategy**: Always use M1 (Calibrated Semi-Auto). It is the most accurate method because it relies on precise axis reference points provided by the user, not AI guessing. M2/M3 can supplement M1 for automated batch processing of clean, high-contrast figures.

---

## Method 1: Calibrated Semi-Auto (Core Method — Always Use This)

Uses multi-point axis calibration + color-based detection for maximum precision. This is the ONLY method that achieves ±0.5% accuracy because it eliminates the largest source of error: axis coordinate mapping.

### Why this method is the most accurate

1. **Human verifies axis reference points** — no AI hallucination of values
2. **Multi-point least-squares fit** — corrects perspective distortion from scanning/screenshots
3. **Sub-pixel centroid refinement** — Gaussian-weighted, inspired by Engauge Digitizer
4. **Color-distance metric** — robust matching in HSV space, inspired by WebPlotDigitizer

### Step 1: Load and view the image

```python
import cv2
img = cv2.imread("figure.png")
```

Use the Read tool to view the figure image. Identify:
- **Chart type**: bar, grouped bar, stacked bar, line, scatter, box, violin, heatmap, pie, polar
- **Axes**: labels, units, scale type (linear / log / log-log / reciprocal / date)
- **Tick marks**: exact values at each tick on both axes
- **Data series**: count, legend labels, visual encoding (color, marker, line style)
- **Markers**: shape (circle, diamond, square, triangle), size, fill — the **geometric center** of each marker is the true data point, not its edge
- **Grid**: major and minor gridlines (may need removal before color detection)

### Step 2: Detect or specify the plot area

Try automatic detection first:

```python
from scripts.figdatax import auto_detect_plot_area
bbox = auto_detect_plot_area("figure.png")
# Returns (left, top, right, bottom) pixel coordinates of the plot area
```

If auto-detection fails or is inaccurate, ask the user for the plot area bounding box, or use an image viewer to determine pixel coordinates.

### Step 3: Multi-point axis calibration

**This is the key step for accuracy.** Use 3+ reference points per axis for error correction via least-squares fit.

Ask the user:
- "What values are at the axis tick marks? (e.g., x-axis: 0, 10, 20, 30, 40; y-axis: 0, 25, 50, 75, 100)"
- Or: "What are the x-range (min, max) and y-range (min, max)?"

Determine pixel coordinates of each tick mark from the image:

```python
from scripts.figdatax import calibrate_axes_multipoint

# Multi-point calibration with least-squares fit
# pixel_points_x: pixel x-coordinates of x-axis tick marks
# data_values_x: corresponding data values
# pixel_points_y: pixel y-coordinates of y-axis tick marks
# data_values_y: corresponding data values
converter = calibrate_axes_multipoint(
    pixel_points_x=[85, 200, 315, 430],
    data_values_x=[0, 10, 20, 30],
    pixel_points_y=[380, 285, 190, 95],
    data_values_y=[0, 25, 50, 75],
    x_log=False, y_log=False
)
# converter(px, py) → (data_x, data_y) with sub-pixel precision
# Check calibration quality:
print(f"X-axis RMSE: {converter.x_rmse:.4f}")
print(f"Y-axis RMSE: {converter.y_rmse:.4f}")
```

For quick 2-point calibration (less accurate but still good):
```python
from scripts.figdatax import calibrate_axes
converter = calibrate_axes(bbox, x_range=(0, 30), y_range=(0, 75))
```

### Step 4: Grid removal (if needed)

Grids interfere with color detection. Remove them:

```python
from scripts.figdatax import remove_grid
cleaned_img = remove_grid(img, grid_color_hsv=(0, 0, 200), method="hough")
# method="hough": Uses Hough Line Transform to detect and remove grid lines
# method="color": Removes pixels matching grid color
# method="adaptive": Combines both approaches
```

### Step 5: Extract data points by color

**Critical: Marker centers are the data points.** Scientific charts often use visible markers (circles, diamonds, squares, triangles) on data points. These markers can be large (10-20px diameter). The true data value corresponds to the **geometric center** of the marker, not its edge or any arbitrary pixel within it. When markers are large, reading the edge instead of the center can introduce errors of 5-10% of the axis range.

**Recommended approach — coordinate grid overlay for manual reading:**
When markers are large or multiple series share the same color (e.g., two black curves distinguished only by line style), automated detection may fail. In such cases, generate a fine coordinate grid overlay on the image and manually read each marker's center pixel coordinates:

```python
import cv2
import numpy as np

img = cv2.imread("figure.png")
overlay = img.copy()
h, w = overlay.shape[:2]

# Draw fine grid (25px spacing) with pixel coordinate labels
for x in range(0, w, 25):
    cv2.line(overlay, (x, 0), (x, h), (200, 200, 200), 1)
    if x % 100 == 0:
        cv2.putText(overlay, str(x), (x+2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 0), 1)
for y in range(0, h, 25):
    cv2.line(overlay, (0, y), (w, y), (200, 200, 200), 1)
    if y % 100 == 0:
        cv2.putText(overlay, str(y), (2, y+12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 0), 1)

cv2.imwrite("debug_fine_grid.png", overlay)
# View this image, then read each marker CENTER's (x_px, y_px)
```

Then build a manual pixel lookup and apply the calibration:
```python
# Manual pixel reading — marker CENTER coordinates
marker_y_pixels = {
    2005: 500,   # read from grid overlay
    2006: 387,
    # ...
}
data = {year: px_to_value(y_px) for year, y_px in marker_y_pixels.items()}
```

**Automated extraction (when markers have distinct colors):**

```python
from scripts.figdatax import extract_by_color_adaptive

centroids = extract_by_color_adaptive(
    cleaned_img,                       # use grid-removed image
    target_hsv=(120, 200, 200),        # target color in HSV
    color_distance=25,                 # color distance threshold
    min_area=8,                        # minimum blob area in pixels
    merge_distance=5,                  # merge nearby detections
    subpixel=True                      # enable sub-pixel refinement
)
# Returns: [(cx, cy, area, confidence), ...] sorted by x
# cx, cy are the centroid (geometric center) of each detected blob
```

**Beware of legend contamination:** If the legend box overlaps with the plot area, its text/symbols can create false detections. Filter by excluding the legend bounding box region.

### Step 6: Convert pixel coordinates to data values

```python
data_points = []
for cx, cy, area, conf in centroids:
    dx, dy = converter(cx, cy)
    data_points.append({"x": dx, "y": dy, "confidence": conf})

import pandas as pd
df = pd.DataFrame(data_points)
df.to_csv("extracted_data.csv", index=False)
print(df)
```

### Step 7: Validate with overlay plot

**Always** generate a validation plot:

```python
from scripts.figdatax import create_validation_plot
create_validation_plot(
    "figure.png",
    [(d["x"], d["y"]) for d in data_points],
    "validation_overlay.png",
    xlabel="X", ylabel="Y",
    title="FigDataX Validation"
)
```

Or build a custom comparison:
```python
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
original_rgb = cv2.cvtColor(cv2.imread("figure.png"), cv2.COLOR_BGR2RGB)
axes[0].imshow(original_rgb)
axes[0].set_title("Original")
axes[0].axis("off")
# ... recreate chart from extracted data on axes[1] ...
axes[1].set_title("Extracted Data (Validation)")
plt.tight_layout()
plt.savefig("validation_overlay.png", dpi=200)
```

---

## Method 2: Fully Automated Color Segmentation

For clean, high-contrast charts with distinct solid colors. Less accurate than M1 because it uses simple bbox-based calibration instead of multi-point calibration.

### Auto-detect dominant colors in the plot area

```python
from scripts.figdatax import detect_data_colors
colors = detect_data_colors(img, plot_bbox, n_clusters=4)
# Returns: [("Series1", (H, S, V)), ("Series2", (H, S, V)), ...]
# Uses K-means clustering on non-background pixels
```

### Auto-extract bar charts

```python
from scripts.figdatax import auto_extract_bars
results = auto_extract_bars(
    img, plot_bbox, y_range=(0, 100),
    colors_hsv={"Treatment": (120, 200, 200), "Control": (0, 200, 200)},
    group_detection=True  # auto-detect grouped bars
)
# Returns: {"Treatment": [45.2, 67.8, 52.1], "Control": [22.4, 41.2, 35.6]}
```

### Auto-extract scatter points

```python
from scripts.figdatax import auto_extract_scatter
points = auto_extract_scatter(
    img, plot_bbox, x_range=(0, 100), y_range=(0, 50),
    target_hsv=(120, 200, 200),
    marker_size_range=(3, 20),
    x_log=False, y_log=False
)
# Returns: [(x1, y1, size), (x2, y2, size), ...]
```

---

## Method 3: Hough + Curve Trace (Line Charts)

Best for line charts with smooth curves. Uses Hough Line Transform and contour-based curve tracing with cubic spline interpolation (inspired by Engauge Digitizer).

### Detect axes via Hough Transform

```python
from scripts.figdatax import detect_axes_hough
axes_info = detect_axes_hough(img)
# Returns: {"x_axis": (x1, y1, x2, y2), "y_axis": (x1, y1, x2, y2),
#           "plot_bbox": (left, top, right, bottom)}
```

### Trace curves by color with sub-pixel interpolation

```python
from scripts.figdatax import trace_curve

curve_points = trace_curve(
    img, plot_bbox,
    target_hsv=(0, 200, 200),  # curve color
    x_range=(0, 100), y_range=(0, 50),
    n_samples=200,               # number of output points
    spline_smoothing=0.01,       # cubic spline smoothing factor
    subpixel=True                # enable sub-pixel centroid refinement
)
# Returns: [(x1, y1), (x2, y2), ...] evenly spaced along the curve
```

### Spline interpolation for sparse points

When only a few points are marked on a curve:
```python
from scripts.figdatax import interpolate_curve
dense_points = interpolate_curve(
    sparse_points=[(0, 10), (25, 35), (50, 42), (75, 38), (100, 30)],
    n_output=200,
    method="cubic_spline"  # or "pchip" for monotone interpolation
)
```

---

## Handling Special Cases

### Log-scale axes (semi-log, log-log)
```python
converter = calibrate_axes_multipoint(..., x_log=True, y_log=True)
# Internally uses: data = 10^(log10_min + fraction * (log10_max - log10_min))
```

### Reciprocal axes (e.g., wavenumber)
```python
converter = calibrate_axes_multipoint(..., x_transform="reciprocal")
# Internally uses: data = 1 / (1/max + fraction * (1/min - 1/max))
```

### Error bars / confidence intervals
```python
from scripts.figdatax import extract_error_bars
points_with_errors = extract_error_bars(
    img, centroids, plot_bbox, y_range,
    error_color_hsv=(0, 0, 0),  # typically black
    search_radius=15
)
# Returns: [(x, y_mean, y_lower, y_upper), ...]
```

### Grouped / stacked bar charts
```python
results = auto_extract_bars(img, plot_bbox, y_range, colors_hsv,
                             group_detection=True, stacked=True)
```

### Multiple panels (a, b, c, d)
```python
from scripts.figdatax import split_panels
panels = split_panels(img, layout="2x2")  # or "1x3", "2x1", auto-detect
# Returns: {"a": img_a, "b": img_b, "c": img_c, "d": img_d}
# Process each panel independently with M1
```

### Polar plots
```python
from scripts.figdatax import extract_polar
polar_data = extract_polar(img, center, r_range, theta_range,
                            target_hsv=(120, 200, 200))
# Returns: [(r1, theta1), (r2, theta2), ...]
```

### Dual Y-axis charts
Process each data series independently:
1. Calibrate left Y-axis with its tick marks
2. Extract data series matching left Y-axis color
3. Calibrate right Y-axis with its tick marks
4. Extract data series matching right Y-axis color

---

## Output Format

Always produce these outputs, saved **in the same directory as the input image**:

1. **Console display**: Print the DataFrame with clear headers and metadata
2. **CSV file**: `{image_stem}_extracted.csv` — data table
3. **Validation plot**: `{image_stem}_validation.png` — side-by-side original vs. reconstructed chart
4. **Optional Excel**: `{image_stem}_extracted.xlsx` with formatted headers if user requests

Output header format:
```
=== FigDataX Extraction Report ===
Source: Figure 2a from Smith et al. (2024)
Chart type: Grouped bar chart
Method: M1 Calibrated Semi-Auto
Calibration RMSE: X=0.0023, Y=0.0015
Points extracted: 12
Estimated accuracy: ±0.8%

  Category  Treatment_A  Treatment_B  Control
  Spring         45.2         38.1    22.4
  ...

Saved to: /path/to/figure2a_extracted.csv
Validation: /path/to/figure2a_validation.png
```

## Precision Best Practices

1. **Resolution matters**: Ask user for highest resolution figure. Extract from PDF as 300+ DPI PNG.
2. **Multi-point calibration**: Use 3+ axis tick marks, not just min/max, to correct for perspective distortion. This is the single most important step for accuracy.
3. **Verify calibration RMSE**: If RMSE is high (>1% of axis range), check for misidentified tick marks.
4. **Marker center = data point**: The geometric center of each marker (circle, diamond, square, triangle) is the true data point. Large markers (10-20px diameter) can introduce 5-10% error if their edge is read instead of their center. Always target the centroid.
5. **Grid removal first**: Always remove grid lines before automated color detection.
6. **Sub-pixel refinement**: Always enable `subpixel=True` for data point detection.
7. **Dual Y-axis**: Calibrate each axis separately with its own tick marks.
8. **Legend contamination**: Filter out false detections from legend box text/symbols that overlap with the plot area. Exclude the legend bounding box region before marker detection.
9. **Same-color curves**: When multiple curves share the same color (e.g., solid vs dashed black lines), automated color-based separation fails. Use the coordinate grid overlay + manual reading approach instead.
10. **Report uncertainty**: State extraction method and calibration RMSE in every output.
11. **Validation overlay**: Always generate — it's the most reliable way to catch errors.
