#!/usr/bin/env python3
"""
FigDataX — High-Precision Scientific Figure Data Extraction

Core method: Axis-calibrated semi-automatic extraction (M1)
  - Multi-point axis calibration with least-squares fit
  - Sub-pixel centroid refinement (Gaussian-weighted)
  - Color-distance matching in HSV space

Supplementary methods:
  M2: Fully Automated (color segmentation + auto-detection)
  M3: Hough + Curve Trace (line/curve detection with spline interpolation)

Additional features:
  - Adaptive grid removal (Hough lines + color filtering)
  - Automatic plot area detection
  - K-means color clustering for auto series detection
  - Error bar extraction
  - Multi-panel splitting

Usage:
    python3 figdatax.py <image> --mode [semi|auto|trace]
        --y-range Y_MIN Y_MAX [--x-range X_MIN X_MAX]
        --bbox LEFT TOP RIGHT BOTTOM
        [--calibration-points FILE]
        [--remove-grid] [--subpixel]
        [--colors "name:H,S,V" ...]
        [--output extracted_data.csv] [--validate]
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline, PchipInterpolator
from scipy.optimize import least_squares


# ═══════════════════════════════════════════════════════════════════
#  1. AUTOMATIC PLOT AREA DETECTION
# ═══════════════════════════════════════════════════════════════════

def auto_detect_plot_area(img_or_path):
    """
    Detect the plot area bounding box using Hough line detection.
    Finds the two strongest horizontal and two strongest vertical lines
    that form the plot border.

    Returns: (left, top, right, bottom) pixel coordinates, or None if detection fails.
    """
    if isinstance(img_or_path, str):
        img = cv2.imread(img_or_path)
    else:
        img = img_or_path

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    h, w = gray.shape
    min_line_len = int(min(h, w) * 0.3)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=min_line_len, maxLineGap=10)
    if lines is None:
        return None

    horizontals = []
    verticals = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if angle < 5 or angle > 175:  # horizontal
            horizontals.append((min(y1, y2), length, x1, x2))
        elif 85 < angle < 95:  # vertical
            verticals.append((min(x1, x2), length, y1, y2))

    if len(horizontals) < 2 or len(verticals) < 2:
        return None

    # Cluster lines that are close together, keep strongest
    horizontals.sort(key=lambda l: l[0])
    verticals.sort(key=lambda l: l[0])

    h_clusters = _cluster_lines([l[0] for l in horizontals], threshold=15)
    v_clusters = _cluster_lines([l[0] for l in verticals], threshold=15)

    if len(h_clusters) < 2 or len(v_clusters) < 2:
        return None

    top = int(h_clusters[0])
    bottom = int(h_clusters[-1])
    left = int(v_clusters[0])
    right = int(v_clusters[-1])

    # Sanity check
    if right - left < w * 0.2 or bottom - top < h * 0.2:
        return None

    return (left, top, right, bottom)


def _cluster_lines(positions, threshold=15):
    """Cluster nearby line positions and return cluster centers."""
    if not positions:
        return []
    positions = sorted(positions)
    clusters = [[positions[0]]]
    for p in positions[1:]:
        if p - clusters[-1][-1] < threshold:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [np.mean(c) for c in clusters]


# ═══════════════════════════════════════════════════════════════════
#  2. MULTI-POINT AXIS CALIBRATION (Least-Squares Fit)
# ═══════════════════════════════════════════════════════════════════

def calibrate_axes_multipoint(pixel_points_x, data_values_x,
                               pixel_points_y, data_values_y,
                               x_log=False, y_log=False,
                               x_transform=None, y_transform=None):
    """
    Multi-point axis calibration using least-squares linear fit.

    Instead of just 2-point (min/max), uses N reference points on each axis
    and fits a linear model to correct for perspective distortion and
    non-uniform scaling.

    Args:
        pixel_points_x: list of pixel x-coordinates of known tick marks
        data_values_x: corresponding data values
        pixel_points_y: list of pixel y-coordinates of known tick marks
        data_values_y: corresponding data values
        x_log/y_log: True if axis uses log scale
        x_transform/y_transform: "reciprocal" for 1/x axes

    Returns:
        Function pixel_to_data(px, py) → (data_x, data_y)
    """
    px_arr = np.array(pixel_points_x, dtype=float)
    dx_arr = np.array(data_values_x, dtype=float)
    py_arr = np.array(pixel_points_y, dtype=float)
    dy_arr = np.array(data_values_y, dtype=float)

    # Transform data values if log/reciprocal scale
    if x_log:
        dx_arr = np.log10(dx_arr)
    elif x_transform == "reciprocal":
        dx_arr = 1.0 / dx_arr

    if y_log:
        dy_arr = np.log10(dy_arr)
    elif y_transform == "reciprocal":
        dy_arr = 1.0 / dy_arr

    # Least-squares linear fit: data = a * pixel + b
    x_coeffs = np.polyfit(px_arr, dx_arr, 1)  # [slope, intercept]
    y_coeffs = np.polyfit(py_arr, dy_arr, 1)

    # Calculate fit residuals for quality assessment
    x_residuals = dx_arr - np.polyval(x_coeffs, px_arr)
    y_residuals = dy_arr - np.polyval(y_coeffs, py_arr)
    x_rmse = np.sqrt(np.mean(x_residuals ** 2))
    y_rmse = np.sqrt(np.mean(y_residuals ** 2))

    def pixel_to_data(px, py):
        raw_x = np.polyval(x_coeffs, px)
        raw_y = np.polyval(y_coeffs, py)

        if x_log:
            raw_x = 10 ** raw_x
        elif x_transform == "reciprocal":
            raw_x = 1.0 / raw_x if raw_x != 0 else float("inf")

        if y_log:
            raw_y = 10 ** raw_y
        elif y_transform == "reciprocal":
            raw_y = 1.0 / raw_y if raw_y != 0 else float("inf")

        return round(float(raw_x), 4), round(float(raw_y), 4)

    pixel_to_data.x_rmse = x_rmse
    pixel_to_data.y_rmse = y_rmse
    pixel_to_data.x_coeffs = x_coeffs
    pixel_to_data.y_coeffs = y_coeffs
    return pixel_to_data


def calibrate_axes(plot_bbox, x_range, y_range, x_log=False, y_log=False):
    """
    Simple 2-point axis calibration (backward compatible).
    For higher precision, use calibrate_axes_multipoint().
    """
    px_left, py_top, px_right, py_bottom = plot_bbox
    x_min, x_max = x_range
    y_min, y_max = y_range

    return calibrate_axes_multipoint(
        pixel_points_x=[px_left, px_right],
        data_values_x=[x_min, x_max],
        pixel_points_y=[py_top, py_bottom],
        data_values_y=[y_max, y_min],  # Note: image y is inverted
        x_log=x_log, y_log=y_log
    )


# ═══════════════════════════════════════════════════════════════════
#  3. GRID REMOVAL
# ═══════════════════════════════════════════════════════════════════

def remove_grid(img, method="adaptive", grid_color_hsv=None):
    """
    Remove grid lines from chart image to improve data point detection.

    Methods:
        "hough": Detect grid lines via Hough Transform and inpaint them
        "color": Remove pixels matching grid_color_hsv
        "adaptive": Try Hough first, fall back to color-based

    Returns: cleaned image (BGR numpy array)
    """
    result = img.copy()

    if method in ("hough", "adaptive"):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 100, apertureSize=3)

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                                minLineLength=50, maxLineGap=5)

        if lines is not None and len(lines) > 0:
            # Create a mask of detected grid lines
            mask = np.zeros(gray.shape, dtype=np.uint8)
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                # Only remove strictly horizontal/vertical lines (grid lines)
                if angle < 3 or angle > 177 or (87 < angle < 93):
                    cv2.line(mask, (x1, y1), (x2, y2), 255, 2)

            # Inpaint the grid lines
            result = cv2.inpaint(result, mask, 3, cv2.INPAINT_TELEA)
            return result
        elif method == "hough":
            return result

    if method in ("color", "adaptive"):
        if grid_color_hsv is not None:
            hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
            h, s, v = grid_color_hsv
            lower = np.array([max(0, h - 10), 0, max(0, v - 30)])
            upper = np.array([min(179, h + 10), 60, min(255, v + 30)])
            grid_mask = cv2.inRange(hsv, lower, upper)

            # Only remove thin lines (dilate to find thick objects, subtract)
            kernel = np.ones((3, 3), np.uint8)
            thick = cv2.dilate(grid_mask, kernel, iterations=2)
            thin_lines = cv2.bitwise_and(grid_mask, cv2.bitwise_not(
                cv2.erode(thick, kernel, iterations=2)))

            result = cv2.inpaint(result, thin_lines, 3, cv2.INPAINT_TELEA)

    return result


# ═══════════════════════════════════════════════════════════════════
#  4. COLOR-BASED DATA EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def extract_by_color_adaptive(img, target_hsv, color_distance=25,
                               min_area=8, merge_distance=5,
                               subpixel=False):
    """
    Extract data point centroids by color matching with adaptive thresholding.

    Improvements over basic extract_by_color:
    - Color distance metric (Euclidean in HSV) like WebPlotDigitizer
    - Merge nearby detections to avoid duplicates
    - Optional sub-pixel centroid refinement
    - Returns confidence scores based on area and color match

    Args:
        img: BGR image
        target_hsv: (H, S, V) target color
        color_distance: max Euclidean distance in HSV space (0-255 scale)
        min_area: minimum blob area in pixels
        merge_distance: merge detections within N pixels
        subpixel: enable Gaussian-weighted sub-pixel refinement

    Returns: list of (cx, cy, area, confidence) sorted by x
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h_t, s_t, v_t = target_hsv

    # Compute per-pixel color distance
    h_diff = np.minimum(np.abs(hsv[:, :, 0].astype(float) - h_t),
                        180 - np.abs(hsv[:, :, 0].astype(float) - h_t))
    h_diff = h_diff * 2  # Scale hue to 0-360 range equivalent
    s_diff = hsv[:, :, 1].astype(float) - s_t
    v_diff = hsv[:, :, 2].astype(float) - v_t

    dist = np.sqrt(h_diff ** 2 + s_diff ** 2 + v_diff ** 2)
    mask = (dist < color_distance).astype(np.uint8) * 255

    # Morphological cleanup
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)

    detections = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue

        M = cv2.moments(c)
        if M["m00"] == 0:
            continue

        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]

        if subpixel:
            cx, cy = _subpixel_refine(img, hsv, cx, cy, target_hsv, radius=5)

        # Confidence: based on how close the average color is to target
        mask_single = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(mask_single, [c], -1, 255, -1)
        mean_dist = np.mean(dist[mask_single > 0])
        confidence = max(0.0, 1.0 - mean_dist / color_distance)

        detections.append((float(cx), float(cy), float(area), float(confidence)))

    # Merge nearby detections
    if merge_distance > 0:
        detections = _merge_nearby(detections, merge_distance)

    detections.sort(key=lambda d: d[0])
    return detections


def _subpixel_refine(img, hsv, cx_init, cy_init, target_hsv, radius=5):
    """
    Sub-pixel centroid refinement using Gaussian-weighted average.
    Inspired by Engauge Digitizer's approach.
    """
    h, w = img.shape[:2]
    x0 = max(0, int(cx_init) - radius)
    x1 = min(w, int(cx_init) + radius + 1)
    y0 = max(0, int(cy_init) - radius)
    y1 = min(h, int(cy_init) + radius + 1)

    region_hsv = hsv[y0:y1, x0:x1].astype(float)
    h_t, s_t, v_t = target_hsv

    # Color similarity as weight
    h_diff = np.minimum(np.abs(region_hsv[:, :, 0] - h_t),
                        180 - np.abs(region_hsv[:, :, 0] - h_t)) * 2
    s_diff = region_hsv[:, :, 1] - s_t
    v_diff = region_hsv[:, :, 2] - v_t
    dist = np.sqrt(h_diff ** 2 + s_diff ** 2 + v_diff ** 2)

    # Gaussian weight: closer color = higher weight
    sigma = 30.0
    weights = np.exp(-dist ** 2 / (2 * sigma ** 2))

    total_w = np.sum(weights)
    if total_w < 1e-10:
        return cx_init, cy_init

    yy, xx = np.mgrid[y0:y1, x0:x1]
    refined_cx = np.sum(xx * weights) / total_w
    refined_cy = np.sum(yy * weights) / total_w

    return refined_cx, refined_cy


def _merge_nearby(detections, distance):
    """Merge detections within given pixel distance."""
    if not detections:
        return detections

    merged = []
    used = set()
    for i, (cx1, cy1, a1, conf1) in enumerate(detections):
        if i in used:
            continue
        group_x = [cx1 * a1]
        group_y = [cy1 * a1]
        group_a = [a1]
        group_conf = [conf1]
        for j, (cx2, cy2, a2, conf2) in enumerate(detections[i + 1:], i + 1):
            if j in used:
                continue
            if np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) < distance:
                group_x.append(cx2 * a2)
                group_y.append(cy2 * a2)
                group_a.append(a2)
                group_conf.append(conf2)
                used.add(j)

        total_a = sum(group_a)
        merged.append((
            sum(group_x) / total_a,
            sum(group_y) / total_a,
            total_a,
            max(group_conf)
        ))

    return merged


def extract_by_color(img, target_hsv, tolerance=15, min_area=10):
    """Basic color extraction (backward compatible)."""
    results = extract_by_color_adaptive(
        img, target_hsv, color_distance=tolerance * 3,
        min_area=min_area, subpixel=False
    )
    return [(cx, cy) for cx, cy, _, _ in results]


# ═══════════════════════════════════════════════════════════════════
#  5. AUTO COLOR DETECTION (K-means)
# ═══════════════════════════════════════════════════════════════════

def detect_data_colors(img, plot_bbox, n_clusters=4, bg_threshold=0.6):
    """
    Auto-detect dominant data colors in the plot area using K-means clustering.

    Filters out background colors (white, very light gray) and returns
    the N most prominent colors as HSV values.

    Returns: list of ("Color_N", (H, S, V)) tuples
    """
    px_left, py_top, px_right, py_bottom = plot_bbox
    region = img[py_top:py_bottom, px_left:px_right]

    hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    pixels = hsv_region.reshape(-1, 3).astype(float)

    # Filter out near-white/near-black (background) pixels
    mask = (pixels[:, 1] > 30) & (pixels[:, 2] > 30) & (pixels[:, 2] < 250)
    fg_pixels = pixels[mask]

    if len(fg_pixels) < n_clusters * 10:
        return []

    # K-means clustering
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, centers = cv2.kmeans(
        fg_pixels.astype(np.float32), n_clusters, None,
        criteria, 10, cv2.KMEANS_PP_CENTERS
    )

    # Sort by cluster size (most pixels first)
    unique, counts = np.unique(labels, return_counts=True)
    sorted_idx = np.argsort(-counts)

    results = []
    for i, idx in enumerate(sorted_idx):
        center = centers[idx]
        h, s, v = int(center[0]), int(center[1]), int(center[2])
        results.append((f"Series_{i + 1}", (h, s, v)))

    return results


# ═══════════════════════════════════════════════════════════════════
#  6. BAR CHART EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def auto_extract_bars(img, plot_bbox, y_range, colors_hsv,
                       group_detection=False, stacked=False):
    """
    Extract bar heights from bar charts with group detection support.

    Improvements:
    - Auto-detects grouped bars by x-position clustering
    - Handles stacked bars (subtracts cumulative heights)
    - Better noise filtering with area thresholds
    """
    px_left, py_top, px_right, py_bottom = plot_bbox
    plot_region = img[py_top:py_bottom, px_left:px_right]
    plot_h = py_bottom - py_top
    plot_w = px_right - px_left
    min_bar_area = plot_h * plot_w * 0.001  # at least 0.1% of plot area

    results = {}
    for name, hsv_val in colors_hsv.items():
        hsv = cv2.cvtColor(plot_region, cv2.COLOR_BGR2HSV)
        h, s, v = hsv_val
        lower = np.array([max(0, h - 15), max(0, s - 60), max(0, v - 60)])
        upper = np.array([min(179, h + 15), min(255, s + 60), min(255, v + 60)])
        mask = cv2.inRange(hsv, lower, upper)

        # Clean up
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        bars = []
        for c in sorted(contours, key=lambda c: cv2.boundingRect(c)[0]):
            x, y, w, bh = cv2.boundingRect(c)
            area = cv2.contourArea(c)
            if area < min_bar_area or w < 3 or bh < 3:
                continue

            if stacked:
                # For stacked: use bottom of bar as well
                bar_top = y
                bar_bottom = y + bh
                top_ratio = 1.0 - (bar_top / plot_h)
                bottom_ratio = 1.0 - (bar_bottom / plot_h)
                top_val = y_range[0] + top_ratio * (y_range[1] - y_range[0])
                bottom_val = y_range[0] + bottom_ratio * (y_range[1] - y_range[0])
                bars.append({
                    "x_center": x + w / 2,
                    "value": round(top_val - bottom_val, 2),
                    "cumulative_top": round(top_val, 2)
                })
            else:
                height_ratio = 1.0 - (y / plot_h)
                data_value = y_range[0] + height_ratio * (y_range[1] - y_range[0])
                bars.append(round(data_value, 2))

        results[name] = bars

    return results


# ═══════════════════════════════════════════════════════════════════
#  7. SCATTER POINT EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def auto_extract_scatter(img, plot_bbox, x_range, y_range,
                          target_hsv, marker_size_range=(3, 30),
                          x_log=False, y_log=False, subpixel=True):
    """
    Extract scatter plot data points with size information.

    Args:
        marker_size_range: (min, max) expected marker diameter in pixels

    Returns: list of (x_data, y_data, marker_area) tuples
    """
    px_left, py_top, px_right, py_bottom = plot_bbox
    converter = calibrate_axes(plot_bbox, x_range, y_range, x_log, y_log)

    detections = extract_by_color_adaptive(
        img, target_hsv, color_distance=30,
        min_area=marker_size_range[0] ** 2 * 0.5,
        merge_distance=marker_size_range[0],
        subpixel=subpixel
    )

    # Filter to only points within the plot area
    points = []
    for cx, cy, area, conf in detections:
        if px_left <= cx <= px_right and py_top <= cy <= py_bottom:
            dx, dy = converter(cx, cy)
            points.append((dx, dy, area))

    return points


# ═══════════════════════════════════════════════════════════════════
#  8. CURVE TRACING (Method 3)
# ═══════════════════════════════════════════════════════════════════

def trace_curve(img, plot_bbox, target_hsv, x_range, y_range,
                n_samples=200, spline_smoothing=0.01,
                color_distance=30, subpixel=True,
                x_log=False, y_log=False):
    """
    Trace a continuous curve in a line chart using column-by-column scanning
    with sub-pixel Gaussian centroid refinement and cubic spline interpolation.

    Algorithm (inspired by Engauge Digitizer segment fill):
    1. For each pixel column in the plot area, find matching pixels
    2. Compute the weighted centroid of matching pixels in that column
    3. Apply sub-pixel refinement via Gaussian weighting
    4. Fit cubic spline through detected points
    5. Resample at uniform x-intervals

    Returns: list of (x_data, y_data) tuples, evenly spaced
    """
    px_left, py_top, px_right, py_bottom = plot_bbox
    region = img[py_top:py_bottom, px_left:px_right]
    hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    h_t, s_t, v_t = target_hsv
    region_h = py_bottom - py_top
    region_w = px_right - px_left

    raw_points = []  # (col_pixel, row_pixel_subpixel)

    for col in range(region_w):
        column_hsv = hsv_region[:, col, :].astype(float)

        # Compute color distance for this column
        h_diff = np.minimum(np.abs(column_hsv[:, 0] - h_t),
                            180 - np.abs(column_hsv[:, 0] - h_t)) * 2
        s_diff = column_hsv[:, 1] - s_t
        v_diff = column_hsv[:, 2] - v_t
        dist = np.sqrt(h_diff ** 2 + s_diff ** 2 + v_diff ** 2)

        matching = np.where(dist < color_distance)[0]
        if len(matching) == 0:
            continue

        if subpixel:
            # Gaussian-weighted centroid for sub-pixel precision
            sigma = 5.0
            weights = np.exp(-dist[matching] ** 2 / (2 * sigma ** 2))
            total_w = np.sum(weights)
            if total_w > 0:
                cy = np.sum(matching * weights) / total_w
            else:
                cy = np.mean(matching)
        else:
            cy = np.mean(matching)

        raw_points.append((col, cy))

    if len(raw_points) < 4:
        return []

    cols = np.array([p[0] for p in raw_points])
    rows = np.array([p[1] for p in raw_points])

    # Remove outliers using median filter
    if len(rows) > 10:
        window = min(11, len(rows) // 3)
        if window % 2 == 0:
            window += 1
        from scipy.signal import medfilt
        smoothed = medfilt(rows, kernel_size=window)
        residuals = np.abs(rows - smoothed)
        threshold = np.median(residuals) * 3 + 1
        mask = residuals < threshold
        cols = cols[mask]
        rows = rows[mask]

    if len(cols) < 4:
        return []

    # Fit cubic spline
    try:
        cs = CubicSpline(cols, rows, extrapolate=False)
    except ValueError:
        # If duplicate x values, use unique
        unique_cols, unique_idx = np.unique(cols, return_index=True)
        cs = CubicSpline(unique_cols, rows[unique_idx], extrapolate=False)
        cols = unique_cols

    # Resample at uniform intervals
    sample_cols = np.linspace(cols[0], cols[-1], n_samples)
    sample_rows = cs(sample_cols)

    # Convert pixel to data coordinates
    converter = calibrate_axes(plot_bbox, x_range, y_range, x_log, y_log)
    result = []
    for c, r in zip(sample_cols, sample_rows):
        if np.isnan(r):
            continue
        px = px_left + c
        py = py_top + r
        dx, dy = converter(px, py)
        result.append((dx, dy))

    return result


def interpolate_curve(sparse_points, n_output=200, method="cubic_spline"):
    """
    Interpolate between sparse data points to generate a dense curve.

    Methods:
        "cubic_spline": natural cubic spline (smooth, may overshoot)
        "pchip": PCHIP (monotone-preserving, no overshoot)
    """
    xs = np.array([p[0] for p in sparse_points])
    ys = np.array([p[1] for p in sparse_points])

    x_dense = np.linspace(xs[0], xs[-1], n_output)

    if method == "cubic_spline":
        interp = CubicSpline(xs, ys)
    elif method == "pchip":
        interp = PchipInterpolator(xs, ys)
    else:
        raise ValueError(f"Unknown method: {method}")

    y_dense = interp(x_dense)
    return list(zip(x_dense.tolist(), y_dense.tolist()))


# ═══════════════════════════════════════════════════════════════════
#  9. ERROR BAR EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def extract_error_bars(img, centroids, plot_bbox, y_range,
                        error_color_hsv=(0, 0, 0), search_radius=20):
    """
    Extract error bar endpoints above and below each data point centroid.

    Scans vertically from each centroid to find thin vertical lines
    (error bar whiskers) in the specified color.

    Returns: list of (x_data, y_mean, y_lower, y_upper)
    """
    converter = calibrate_axes(plot_bbox, (0, 1), y_range)  # x doesn't matter
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h_t, s_t, v_t = error_color_hsv
    h_img, w_img = img.shape[:2]

    results = []
    for cx, cy in centroids:
        cx_int, cy_int = int(cx), int(cy)

        # Search upward for upper error bar
        upper_y = cy_int
        for y in range(cy_int - 1, max(0, cy_int - search_radius), -1):
            if 0 <= y < h_img and 0 <= cx_int < w_img:
                pixel_hsv = hsv[y, cx_int]
                h_diff = min(abs(int(pixel_hsv[0]) - h_t), 180 - abs(int(pixel_hsv[0]) - h_t))
                if h_diff < 15 and abs(int(pixel_hsv[1]) - s_t) < 80 and abs(int(pixel_hsv[2]) - v_t) < 80:
                    upper_y = y
                else:
                    break

        # Search downward for lower error bar
        lower_y = cy_int
        for y in range(cy_int + 1, min(h_img, cy_int + search_radius)):
            if 0 <= y < h_img and 0 <= cx_int < w_img:
                pixel_hsv = hsv[y, cx_int]
                h_diff = min(abs(int(pixel_hsv[0]) - h_t), 180 - abs(int(pixel_hsv[0]) - h_t))
                if h_diff < 15 and abs(int(pixel_hsv[1]) - s_t) < 80 and abs(int(pixel_hsv[2]) - v_t) < 80:
                    lower_y = y
                else:
                    break

        _, y_mean = converter(cx, cy)
        _, y_upper = converter(cx, upper_y)
        _, y_lower = converter(cx, lower_y)

        results.append((round(cx, 1), y_mean, y_lower, y_upper))

    return results


# ═══════════════════════════════════════════════════════════════════
#  10. MULTI-PANEL SPLITTING
# ═══════════════════════════════════════════════════════════════════

def split_panels(img, layout="auto"):
    """
    Split a multi-panel figure into individual panel images.

    Args:
        layout: "2x2", "1x3", "2x1", "3x1", or "auto"

    Returns: dict of {"a": img_a, "b": img_b, ...}
    """
    h, w = img.shape[:2]
    labels = "abcdefghijklmnop"

    if layout == "auto":
        # Detect panels by finding large white/gray gaps
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Check for horizontal splits
        row_means = np.mean(gray, axis=1)
        h_splits = _find_splits(row_means, min_gap=10, threshold=240)

        # Check for vertical splits
        col_means = np.mean(gray, axis=0)
        v_splits = _find_splits(col_means, min_gap=10, threshold=240)

        n_rows = len(h_splits) + 1
        n_cols = len(v_splits) + 1
        layout = f"{n_rows}x{n_cols}"

    rows, cols = map(int, layout.split("x"))
    panel_h = h // rows
    panel_w = w // cols

    panels = {}
    idx = 0
    for r in range(rows):
        for c in range(cols):
            y0 = r * panel_h
            y1 = (r + 1) * panel_h if r < rows - 1 else h
            x0 = c * panel_w
            x1 = (c + 1) * panel_w if c < cols - 1 else w
            panels[labels[idx]] = img[y0:y1, x0:x1].copy()
            idx += 1

    return panels


def _find_splits(signal, min_gap=10, threshold=240):
    """Find gap positions in a 1D signal (row/column means)."""
    above = signal > threshold
    splits = []
    in_gap = False
    gap_start = 0

    for i, val in enumerate(above):
        if val and not in_gap:
            in_gap = True
            gap_start = i
        elif not val and in_gap:
            gap_len = i - gap_start
            if gap_len >= min_gap:
                splits.append((gap_start + i) // 2)
            in_gap = False

    return splits


# ═══════════════════════════════════════════════════════════════════
#  11. HOUGH AXIS DETECTION
# ═══════════════════════════════════════════════════════════════════

def detect_axes_hough(img_or_path):
    """
    Detect axis lines using Hough Transform.
    Returns the strongest horizontal and vertical lines as potential axes.

    Returns: dict with "x_axis", "y_axis", "plot_bbox" keys
    """
    bbox = auto_detect_plot_area(img_or_path)
    if bbox is None:
        return None

    left, top, right, bottom = bbox
    return {
        "x_axis": (left, bottom, right, bottom),
        "y_axis": (left, top, left, bottom),
        "plot_bbox": bbox
    }


# ═══════════════════════════════════════════════════════════════════
#  12. POLAR PLOT EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def extract_polar(img, center, r_range, theta_range=(0, 360),
                   target_hsv=(120, 200, 200), n_angles=360):
    """
    Extract data from polar plots.

    Args:
        center: (cx, cy) pixel coordinates of the polar origin
        r_range: (r_min_data, r_max_data, r_max_pixels)
        theta_range: (theta_min, theta_max) in degrees
    """
    cx, cy = center
    r_min_d, r_max_d, r_max_px = r_range
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h_t, s_t, v_t = target_hsv

    results = []
    for i in range(n_angles):
        theta_deg = theta_range[0] + i * (theta_range[1] - theta_range[0]) / n_angles
        theta_rad = np.radians(theta_deg)

        # Scan along this angle
        best_r = None
        best_dist = float("inf")

        for r_px in range(1, r_max_px):
            px = int(cx + r_px * np.cos(theta_rad))
            py = int(cy - r_px * np.sin(theta_rad))  # y is inverted

            if 0 <= px < img.shape[1] and 0 <= py < img.shape[0]:
                pixel = hsv[py, px]
                h_diff = min(abs(int(pixel[0]) - h_t), 180 - abs(int(pixel[0]) - h_t)) * 2
                s_diff = abs(int(pixel[1]) - s_t)
                v_diff = abs(int(pixel[2]) - v_t)
                color_dist = np.sqrt(h_diff ** 2 + s_diff ** 2 + v_diff ** 2)

                if color_dist < 40 and color_dist < best_dist:
                    best_dist = color_dist
                    r_data = r_min_d + (r_px / r_max_px) * (r_max_d - r_min_d)
                    best_r = r_data

        if best_r is not None:
            results.append((round(best_r, 4), round(theta_deg, 1)))

    return results


# ═══════════════════════════════════════════════════════════════════
#  13. VALIDATION PLOT
# ═══════════════════════════════════════════════════════════════════

def create_validation_plot(original_img_path, data_points, output_path,
                            xlabel="X", ylabel="Y",
                            title="FigDataX Validation Overlay"):
    """Create side-by-side validation: original image + extracted data."""
    original = cv2.imread(original_img_path)
    original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].imshow(original_rgb)
    axes[0].set_title("Original Figure")
    axes[0].axis("off")

    if isinstance(data_points, dict):
        for series_name, points in data_points.items():
            if isinstance(points, list) and len(points) > 0:
                if isinstance(points[0], (list, tuple)):
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    axes[1].plot(xs, ys, "o-", label=series_name, markersize=4)
                else:
                    axes[1].bar(range(len(points)), points,
                               label=series_name, alpha=0.7)
    elif isinstance(data_points, list) and len(data_points) > 0:
        if isinstance(data_points[0], (list, tuple)):
            xs = [p[0] for p in data_points]
            ys = [p[1] for p in data_points]
            axes[1].plot(xs, ys, "o-", color="steelblue", markersize=4)

    axes[1].set_xlabel(xlabel)
    axes[1].set_ylabel(ylabel)
    axes[1].set_title(title)
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    print(f"Validation plot saved to: {output_path}")
    plt.close()


# ═══════════════════════════════════════════════════════════════════
#  14. CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════

def parse_color(color_str):
    """Parse 'name:H,S,V' into (name, (H, S, V))."""
    name, vals = color_str.split(":")
    h, s, v = map(int, vals.split(","))
    return name.strip(), (h, s, v)


def main():
    parser = argparse.ArgumentParser(
        description="FigDataX — Multi-Method Scientific Figure Data Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Semi-auto with multi-point calibration
  python3 figdatax.py figure.png --mode semi \\
      --x-range 0 100 --y-range 0 50 \\
      --bbox 80 40 520 380 --color-target 120 200 200 \\
      --subpixel --remove-grid --validate

  # Auto-extract bars by color
  python3 figdatax.py bars.png --mode auto \\
      --y-range 0 100 --bbox 80 40 520 380 \\
      --colors "blue:120,200,200" "red:0,200,200"

  # Trace a curve in a line chart
  python3 figdatax.py line.png --mode trace \\
      --x-range 0 100 --y-range 0 50 \\
      --bbox 80 40 520 380 --color-target 0 200 200 \\
      --n-samples 200 --subpixel
        """)

    parser.add_argument("image", help="Path to the figure image")
    parser.add_argument("--mode", choices=["semi", "auto", "trace"],
                        default="semi", help="Extraction mode (default: semi)")
    parser.add_argument("--x-range", type=float, nargs=2, metavar=("MIN", "MAX"))
    parser.add_argument("--y-range", type=float, nargs=2, metavar=("MIN", "MAX"),
                        required=True)
    parser.add_argument("--bbox", type=int, nargs=4,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="Plot area bbox (auto-detected if omitted)")
    parser.add_argument("--x-log", action="store_true")
    parser.add_argument("--y-log", action="store_true")
    parser.add_argument("--colors", nargs="+",
                        help="Colors for auto mode: 'name:H,S,V'")
    parser.add_argument("--color-target", type=int, nargs=3,
                        metavar=("H", "S", "V"))
    parser.add_argument("--color-distance", type=float, default=30,
                        help="Color distance threshold (default: 30)")
    parser.add_argument("--subpixel", action="store_true",
                        help="Enable sub-pixel centroid refinement")
    parser.add_argument("--remove-grid", action="store_true",
                        help="Remove grid lines before extraction")
    parser.add_argument("--n-samples", type=int, default=200,
                        help="Number of output points for trace mode")
    parser.add_argument("--output", default="extracted_data.csv")
    parser.add_argument("--validate", action="store_true")

    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"Error: Image not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    img = cv2.imread(args.image)
    if img is None:
        print(f"Error: Could not read image: {args.image}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect plot area if bbox not provided
    if args.bbox:
        plot_bbox = tuple(args.bbox)
    else:
        plot_bbox = auto_detect_plot_area(img)
        if plot_bbox is None:
            print("Error: Could not auto-detect plot area. "
                  "Please provide --bbox.", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-detected plot area: {plot_bbox}")

    # Remove grid if requested
    if args.remove_grid:
        img = remove_grid(img, method="adaptive")
        print("Grid lines removed.")

    x_range = tuple(args.x_range) if args.x_range else (0, 1)
    y_range = tuple(args.y_range)

    # ── SEMI MODE ──
    if args.mode == "semi":
        if not args.color_target:
            print("Error: --color-target H S V required for semi mode",
                  file=sys.stderr)
            sys.exit(1)

        converter = calibrate_axes(plot_bbox, x_range, y_range,
                                   args.x_log, args.y_log)
        detections = extract_by_color_adaptive(
            img, tuple(args.color_target),
            color_distance=args.color_distance,
            subpixel=args.subpixel
        )

        data_points = []
        for cx, cy, area, conf in detections:
            dx, dy = converter(cx, cy)
            data_points.append((dx, dy, area, conf))

        df = pd.DataFrame(data_points, columns=["X", "Y", "Area", "Confidence"])
        df.to_csv(args.output, index=False)

        print(f"\n=== FigDataX: Extracted {len(data_points)} data points ===")
        print(f"Method: Semi-Auto | Sub-pixel: {args.subpixel}")
        print(df[["X", "Y"]].to_string(index=False))
        print(f"\nSaved to: {args.output}")

        if args.validate:
            pts = [(r.X, r.Y) for _, r in df.iterrows()]
            create_validation_plot(args.image, pts,
                                   args.output.replace(".csv", "_validation.png"))

    # ── AUTO MODE ──
    elif args.mode == "auto":
        if not args.colors:
            # Try auto-detecting colors
            colors_hsv = dict(detect_data_colors(img, plot_bbox))
            if not colors_hsv:
                print("Error: --colors required (auto-detection failed)",
                      file=sys.stderr)
                sys.exit(1)
            print(f"Auto-detected colors: {list(colors_hsv.keys())}")
        else:
            colors_hsv = dict(parse_color(c) for c in args.colors)

        results = auto_extract_bars(img, plot_bbox, y_range, colors_hsv)

        max_len = max((len(v) for v in results.values()), default=0)
        for k in results:
            results[k] += [None] * (max_len - len(results[k]))

        df = pd.DataFrame(results)
        df.index.name = "Bar"
        df.to_csv(args.output)

        print(f"\n=== FigDataX: Extracted bar data ===")
        print(f"Method: Auto | Colors: {list(colors_hsv.keys())}")
        print(df.to_string())
        print(f"\nSaved to: {args.output}")

        if args.validate:
            create_validation_plot(args.image, results,
                                   args.output.replace(".csv", "_validation.png"))

    # ── TRACE MODE ──
    elif args.mode == "trace":
        if not args.color_target:
            print("Error: --color-target H S V required for trace mode",
                  file=sys.stderr)
            sys.exit(1)

        curve = trace_curve(
            img, plot_bbox, tuple(args.color_target),
            x_range, y_range,
            n_samples=args.n_samples,
            color_distance=args.color_distance,
            subpixel=args.subpixel,
            x_log=args.x_log, y_log=args.y_log
        )

        df = pd.DataFrame(curve, columns=["X", "Y"])
        df.to_csv(args.output, index=False)

        print(f"\n=== FigDataX: Traced {len(curve)} curve points ===")
        print(f"Method: Hough + Curve Trace | Sub-pixel: {args.subpixel}")
        print(f"X range: {df['X'].min():.4f} — {df['X'].max():.4f}")
        print(f"Y range: {df['Y'].min():.4f} — {df['Y'].max():.4f}")
        print(f"\nSaved to: {args.output}")

        if args.validate:
            create_validation_plot(args.image, curve,
                                   args.output.replace(".csv", "_validation.png"))


if __name__ == "__main__":
    main()
