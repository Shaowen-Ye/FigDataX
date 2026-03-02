# FigDataX

**Fig**ure **Data** e**X**traction

高精度科学图表数据提取 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 技能。从论文图表（柱状图、折线图、散点图、箱线图、热力图、饼图、极坐标图、堆叠图）中提取数值数据，精度可达 **±0.5%**。

High-precision scientific figure data extraction skill for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Extract numerical data from paper figures (bar, line, scatter, box, heatmap, pie, polar, stacked charts) with up to **±0.5% accuracy**.

---

## 中文说明

### 工作原理

FigDataX 是一个 Claude Code 技能，引导 AI 完成严格的半自动提取流程：

1. **加载并分析**图像（图表类型、坐标轴、标记、图例）
2. **自动检测绘图区域**或手动指定
3. **多点轴校准** — 在每条轴上取 3+ 个刻度点进行最小二乘拟合
4. **去除网格线** — Hough 线检测或颜色过滤
5. **提取数据点** — 颜色匹配 + 亚像素质心精修，或从坐标网格叠加图手动读取
6. **像素→数据转换** — 使用校准模型
7. **验证** — 原图 vs 重建图并排对比

### 核心原则：标记中心

标记点（圆形、菱形、方形、三角形）的**几何中心**才是真正的数据点。大标记（10-20px）如果读边缘而非中心，可引入 5-10% 误差。

### 安装

```bash
# 复制到 Claude Code skills 目录
cp -r FigDataX ~/.claude/skills/

# 安装 Python 依赖
pip install opencv-python numpy pandas matplotlib scipy openpyxl scikit-image
```

### 使用方法

#### 在 Claude Code 中使用（推荐）

直接告诉 Claude Code 提取图片数据：

```
> 提取 /path/to/figure.png 图片数据
> 从 ./results/fig3.png 中读取数据
> Extract data from /path/to/figure.png
```

Claude Code 将自动完成：
1. 读取图像，识别图表类型、坐标轴、标记
2. 生成坐标网格叠加图用于精确像素读取
3. 执行多点轴校准
4. 提取数据点（标记中心）
5. 将结果和验证图保存在**输入图片所在目录**

#### 文件路径与输出

- **输入**：提供图片文件的绝对或相对路径（PNG、JPG 等）
- **输出**：所有生成文件保存在**输入图片所在的目录**（不是 skill 目录）

| 输出文件 | 说明 |
|----------|------|
| `{图片名}_extracted.csv` | 提取的数据表 |
| `{图片名}_validation.png` | 原图 vs 重建图对比验证 |
| `{图片名}_grid.png` | 坐标网格叠加图（中间文件） |

示例：
```
输入：~/papers/fig3.png
输出：~/papers/fig3_extracted.csv
      ~/papers/fig3_validation.png
      ~/papers/fig3_grid.png
```

#### 批量提取

指向包含多张图的文件夹：
```
> 提取 /path/to/figures/ 文件夹中所有图片的数据
```

#### Python API（独立使用）

在 Claude Code 之外使用 FigDataX Python 库：

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/FigDataX"))
from scripts.figdatax import calibrate_axes_multipoint, auto_detect_plot_area
```

### 提取方法

| 方法 | 名称 | 适用场景 | 精度 |
|------|------|----------|------|
| **M1** | **校准半自动** | **所有图表（默认首选）** | **±0.5-2%** |
| M2 | 全自动颜色分割 | 高对比度、颜色分明的图表 | ±0.5-1% |
| M3 | Hough + 曲线追踪 | 折线图、连续曲线 | ±0.5-1% |

**始终使用 M1。** 这是最精确的方法，因为它依赖用户验证的精确坐标轴参考点，而非 AI 猜测。

### 支持的图表类型

- 柱状图（简单、分组、堆叠）
- 折线图（单系列/多系列）
- 散点图
- 箱线图 / 小提琴图
- 热力图
- 饼图
- 极坐标图
- 双 Y 轴图表
- 多面板图 (a, b, c, d)

### 特殊坐标轴

- 线性、对数（半对数、双对数）
- 倒数（如波数）
- 日期/时间轴

### 最佳实践

1. 使用最高分辨率图像（PDF 导出 300+ DPI）
2. 每轴 3+ 刻度的多点校准
3. 始终读取标记**中心**，而非边缘
4. 颜色检测前先去除网格线
5. 排除图例区域以避免误检
6. 同色曲线使用坐标网格叠加图 + 手动读取
7. 始终生成验证叠加图

---

## English

### How It Works

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

### Installation

```bash
# Copy into your Claude Code skills directory
cp -r FigDataX ~/.claude/skills/

# Install Python dependencies
pip install opencv-python numpy pandas matplotlib scipy openpyxl scikit-image
```

### Usage

#### With Claude Code (Recommended)

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

#### File Paths & Output

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

#### Batch Extraction

To extract from multiple figures in a folder, point Claude Code to the directory:

```
> Extract data from all figures in /path/to/figures/
```

#### Python API (Standalone)

To use FigDataX as a Python library outside Claude Code:

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/FigDataX"))
from scripts.figdatax import calibrate_axes_multipoint, auto_detect_plot_area
```

### Extraction Methods

| Method | Name | Best For | Accuracy |
|--------|------|----------|----------|
| **M1** | **Calibrated Semi-Auto** | **All charts (default)** | **±0.5-2%** |
| M2 | Fully Automated | High-contrast, distinct-color charts | ±0.5-1% |
| M3 | Hough + Curve Trace | Line charts, continuous curves | ±0.5-1% |

**Always use M1.** It is the most accurate because it relies on precise axis reference points verified by the user, not AI guessing.

### Python API

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/FigDataX"))

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
    generate_grid_overlay,       # 3-level coordinate grid overlay generation
    detect_markers_morphological,# Morphological marker detection (same-color series)
    cluster_markers_by_x,        # Group markers by X position
    assign_series_with_crossover,# Series assignment with crossover tracking
    create_validation_plot,      # Validation overlay generation
)
```

#### Quick Example

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/FigDataX"))
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

### CLI Usage

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

### Supported Chart Types

- Bar charts (simple, grouped, stacked)
- Line charts (single/multi-series)
- Scatter plots
- Box plots / violin plots
- Heatmaps
- Pie charts
- Polar plots
- Dual Y-axis charts
- Multi-panel figures (a, b, c, d)

### Special Axis Types

- Linear, logarithmic (semi-log, log-log)
- Reciprocal (e.g., wavenumber)
- Date/time axes

### Best Practices

1. Use highest resolution images (300+ DPI from PDF)
2. Multi-point calibration with 3+ tick marks per axis
3. Always read marker **centers**, not edges
4. Remove grid lines before color-based extraction
5. Filter out legend box area to avoid false detections
6. For same-color curves, use coordinate grid overlay + manual reading
7. Always generate validation overlay plots

---

## File Structure / 文件结构

```
FigDataX/
├── README.md              # 本文件 / This file
├── SKILL.md               # Claude Code skill 定义 (English)
├── 中文说明.md            # 中文参考文档 / Chinese reference
├── requirements.txt       # Python 依赖 / Dependencies
├── LICENSE                # MIT 开源协议 / License
└── scripts/
    ├── __init__.py
    └── figdatax.py        # 核心库 / Core library (16 functions + CLI)
```

## Inspired By / 灵感来源

- [Engauge Digitizer](https://markummitchell.github.io/engauge-digitizer/) — 亚像素质心精修、曲线追踪 / sub-pixel centroid refinement, curve tracing
- [WebPlotDigitizer](https://automeris.io/WebPlotDigitizer/) — HSV 空间颜色距离度量 / color distance metric in HSV space

## License / 许可证

MIT License. See [LICENSE](LICENSE).
