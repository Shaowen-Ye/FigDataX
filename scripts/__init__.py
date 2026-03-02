"""FigDataX — High-Precision Scientific Figure Data Extraction."""

from .figdatax import (
    auto_detect_plot_area,
    calibrate_axes_multipoint,
    calibrate_axes,
    remove_grid,
    extract_by_color_adaptive,
    detect_data_colors,
    auto_extract_bars,
    auto_extract_scatter,
    trace_curve,
    interpolate_curve,
    extract_error_bars,
    split_panels,
    detect_axes_hough,
    extract_polar,
    generate_grid_overlay,
    detect_markers_morphological,
    cluster_markers_by_x,
    assign_series_with_crossover,
    create_validation_plot,
)
