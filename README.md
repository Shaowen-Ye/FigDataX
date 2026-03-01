# FigDataX

**Fig**ure **Data** e**X**traction — High-precision scientific figure data extraction for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Extract numerical data from scientific paper figures (bar, line, scatter, box, heatmap, pie, polar, stacked charts) with up to **±0.5% accuracy**.

## How It Works

FigDataX is a Claude Code skill that guides the AI through a rigorous semi-automatic extraction pipeline:

1. **Load & analyze** the figure image (chart type, axes, markers, legend)
2. **Detect plot area** automatically or via manual specification
3. **Multi-point axis calibration** using least-squares fit on 3+ tick marks per axis
4. **Grid removal** via Hough line detection or color-based filtering
5. **Data point extraction** by color matching with sub-pixel centroid refinement, or manual reading from a coordinate grid overlay
6. **Pixel-to-data conversion** using the calibrated axis model
7. **Validation** via side-by-side overlay plot (original vs. reconstructed)

### Core Principle: Marker Centers

The geometric center of each marker (circle, diamond, square, triangle) is the true data point. Large markers (10-20px) can introduce 5-10% error if edges are read instead of centers.

## Installation

### As a Claude Code Skill

```bash
# Copy into your Claude Code skills directory
cp -r figdatax ~/.claude/skills/
```

### Python Dependencies

```bash
pip install opencv-python numpy pandas matplotlib scipy openpyxl scikit-image
```

## Usage

### With Claude Code (Recommended)

Simply tell Claude Code to extract data from a figure image:

```
> Extract data from /path/to/figure.png
> 提取 /path/to/papers/fig3.png 图片数据
> Digitize the chart in ./results/figure2a.png
```

Claude Code will automatically:
1. Read the image and identify chart type, axes, markers
2. Generate a coordinate grid overlay for precise pixel reading
3. Perform multi-point axis calibration
4. Extract data points (marker centers)
5. Save results and validation plot **in the same directory as the input image**

### File Paths & Output

- **Input**: Provide the absolute or relative path to the figure image (PNG, JPG, etc.)
- **Output**: All generated files are saved **next to the input image**, not in the skill directory

| Output File | Description |
|-------------|-------------|
| `{name}_extracted.csv` | Extracted data table |
| `{name}_validation.png` | Side-by-side original vs. reconstructed chart |
| `{name}_grid.png` | Coordinate grid overlay (intermediate) |

Example:
```
Input:  ~/papers/fig3.png
Output: ~/papers/fig3_extracted.csv
        ~/papers/fig3_validation.png
        ~/papers/fig3_grid.png
```

### Batch Extraction

To extract from multiple figures in a folder, point Claude Code to the directory:

```
> Extract data from all figures in /path/to/figures/
```

Each figure's outputs are saved alongside the original image.

### Python API (Standalone)

To use FigDataX as a Python library outside Claude Code, add the skill directory to your path:

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/figdatax"))
from scripts.figdatax import calibrate_axes_multipoint, auto_detect_plot_area
```

## Extraction Methods

| Method | Name | Best For | Accuracy |
|--------|------|----------|----------|
| **M1** | **Calibrated Semi-Auto** | **All charts (default)** | **±0.5-2%** |
| M2 | Fully Automated | High-contrast, distinct-color charts | ±0.5-1% |
| M3 | Hough + Curve Trace | Line charts, continuous curves | ±0.5-1% |

**Always use M1.** It is the most accurate because it relies on precise axis reference points verified by the user, not AI guessing.

## Python API

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/figdatax"))

from scripts.figdatax import (
    auto_detect_plot_area,       # Automatic plot area detection
    calibrate_axes_multipoint,   # Multi-point least-squares axis calibration
    calibrate_axes,              # Simple 2-point calibration
    remove_grid,                 # Grid line removal (Hough/color/adaptive)
    extract_by_color_adaptive,   # Color-based data extraction with sub-pixel refinement
    detect_data_colors,          # K-means auto color detection
    auto_extract_bars,           # Bar chart extraction
    auto_extract_scatter,        # Scatter plot extraction
    trace_curve,                 # Continuous curve tracing
    interpolate_curve,           # Spline interpolation for sparse points
    extract_error_bars,          # Error bar endpoint extraction
    split_panels,                # Multi-panel figure splitting
    detect_axes_hough,           # Hough-based axis detection
    extract_polar,               # Polar plot extraction
    create_validation_plot,      # Validation overlay generation
)
```

### Quick Example

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/figdatax"))
from scripts.figdatax import calibrate_axes_multipoint

# Calibrate using tick mark positions
converter = calibrate_axes_multipoint(
    pixel_points_x=[85, 200, 315, 430],
    data_values_x=[0, 10, 20, 30],
    pixel_points_y=[380, 285, 190, 95],
    data_values_y=[0, 25, 50, 75]
)

# Convert any pixel coordinate to data values
x, y = converter(250, 240)
print(f"Data point: ({x}, {y})")
print(f"Calibration RMSE: X={converter.x_rmse:.4f}, Y={converter.y_rmse:.4f}")
```

## CLI Usage

```bash
# Semi-auto extraction
python3 scripts/figdatax.py figure.png --mode semi \
    --x-range 0 100 --y-range 0 50 \
    --bbox 80 40 520 380 --color-target 120 200 200 \
    --subpixel --remove-grid --validate

# Auto-extract bar charts
python3 scripts/figdatax.py bars.png --mode auto \
    --y-range 0 100 --bbox 80 40 520 380 \
    --colors "blue:120,200,200" "red:0,200,200"

# Trace a curve
python3 scripts/figdatax.py line.png --mode trace \
    --x-range 0 100 --y-range 0 50 \
    --bbox 80 40 520 380 --color-target 0 200 200 \
    --n-samples 200 --subpixel
```

## Supported Chart Types

- Bar charts (simple, grouped, stacked)
- Line charts (single/multi-series)
- Scatter plots
- Box plots / violin plots
- Heatmaps
- Pie charts
- Polar plots
- Dual Y-axis charts
- Multi-panel figures (a, b, c, d)

## Special Axis Types

- Linear, logarithmic (semi-log, log-log)
- Reciprocal (e.g., wavenumber)
- Date/time axes

## Best Practices

1. Use highest resolution images (300+ DPI from PDF)
2. Multi-point calibration with 3+ tick marks per axis
3. Always read marker **centers**, not edges
4. Remove grid lines before color-based extraction
5. Filter out legend box area to avoid false detections
6. For same-color curves, use coordinate grid overlay + manual reading
7. Always generate validation overlay plots

## File Structure

```
figdatax/
├── README.md              # This file
├── SKILL.md               # Claude Code skill definition (English)
├── 中文说明.md            # Chinese reference documentation
├── requirements.txt       # Python dependencies
├── LICENSE                # MIT License
└── scripts/
    ├── __init__.py
    └── figdatax.py        # Core library (16 public functions + CLI)
```

## Inspired By

- [Engauge Digitizer](https://markummitchell.github.io/engauge-digitizer/) — sub-pixel centroid refinement, curve tracing
- [WebPlotDigitizer](https://automeris.io/WebPlotDigitizer/) — color distance metric in HSV space

## License

MIT License. See [LICENSE](LICENSE).
