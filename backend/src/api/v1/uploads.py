import sys
import time
from pathlib import Path
from typing import List

import cv2
import numpy as np
import networkx as nx
import shapely.geometry as sg
from shapely.validation import make_valid
from fastapi import APIRouter, UploadFile, File, HTTPException

# Add project root to sys.path to allow imports from shared/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.schemas.spatial_graph import (
    SpatialGraphResponse,
    GeometryItem,
    TopologyGraph,
    TopologyNode,
    TopologyEdge,
)

router = APIRouter()

@router.post("/uploads", response_model=SpatialGraphResponse)
async def upload_floorplan(file: UploadFile = File(...)):
    # Validate file format
    filename = file.filename or ""
    if not (filename.lower().endswith('.png') or filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg')):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Only PNG, JPG, and JPEG images are allowed."
        )

    start_time = time.perf_counter()

    try:
        image_bytes = await file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error reading image: {str(e)}"
        )

    if img is None:
        raise HTTPException(
            status_code=400,
            detail="Failed to decode image. Ensure the file is a valid PNG or JPG."
        )

    orig_h, orig_w = img.shape

    # STAGE 0: SCALE-INVARIANT RESIZING
    # Resize image to standard max dimension for stable CV thresholding & classification
    max_dim = 1200.0
    scale = 1.0
    if max(orig_h, orig_w) > max_dim:
        scale = max_dim / max(orig_h, orig_w)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        img_resized = img.copy()

    # Auto-detect dark mode/inverted floorplan images using median intensity relative to range
    min_val, max_val = float(img_resized.min()), float(img_resized.max())
    median_val = float(np.median(img_resized))
    midpoint = (min_val + max_val) / 2.0
    
    # If the majority of pixels are dark (median below midpoint), it's a dark background image.
    # We invert it to normalize walls as dark lines and empty spaces as light backgrounds.
    if median_val <= midpoint:
        img_resized = 255 - img_resized
        min_val, max_val = float(img_resized.min()), float(img_resized.max())

    # STAGE 1: GEOMETRY EXTRACTION & CLEANUP (OpenCV & Shapely)
    # Binarize image dynamically: walls/lines are white (255) in thresh_inv, empty space is black (0)
    if max_val - min_val > 1.0:
        thresh_val = min_val + 0.85 * (max_val - min_val)
    else:
        thresh_val = 220.0
    _, thresh_inv = cv2.threshold(img_resized, thresh_val, 255, cv2.THRESH_BINARY_INV)

    # Morphological Opening to remove thin lines (grid lines, desk outlines, annotations)
    # This keeps only thick structural walls (calibrated to 3x3 to preserve thin partition walls)
    wall_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thick_walls = cv2.morphologyEx(thresh_inv, cv2.MORPH_OPEN, wall_kernel)

    # Thickening walls to seal doorways and windows (prevent leaks)
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    walls_dilated = cv2.dilate(thick_walls, kernel_dilate, iterations=2)

    # Invert to get spaces map (rooms/spaces are white (255), walls are black (0))
    spaces_thick = cv2.bitwise_not(walls_dilated)
    h_p, w_p = spaces_thick.shape

    # Find Canny edges on original resized image to analyze interior furniture/steps
    edges = cv2.Canny(img_resized, 50, 150)

    # Compute Sobel gradients to analyze line parallelism for stairs identification
    sobelx = cv2.Sobel(img_resized, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(img_resized, cv2.CV_64F, 0, 1, ksize=3)

    # Find contours directly on spaces_thick (no flood-fill, avoiding catastrophic leak blackout)
    # Using RETR_CCOMP to organize into a 2-level hierarchy (components vs holes)
    contours, hierarchy = cv2.findContours(spaces_thick, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    geometry_items: List[GeometryItem] = []
    poly_objects = {}  # Map geometry id -> Shapely polygon object
    
    # Thresholds scaled to resized image
    min_area_thresh = 400.0  # pixels
    max_area_thresh = 0.95 * h_p * w_p
    total_area = h_p * w_p

    geom_id_counter = 1

    for i, cnt in enumerate(contours):
        # Ignore holes (e.g. walls, furniture) - only keep component outer boundaries
        if hierarchy is not None and hierarchy[0, i, 3] != -1:
            continue
        area = cv2.contourArea(cnt)
        if area < min_area_thresh or area > max_area_thresh:
            continue

        # Filter out the outer page background / margins.
        # Background contours contain the outer corner regions of the image or have massive area.
        is_background = (
            cv2.pointPolygonTest(cnt, (5, 5), False) >= 0 or
            cv2.pointPolygonTest(cnt, (w_p - 5, 5), False) >= 0 or
            cv2.pointPolygonTest(cnt, (5, h_p - 5), False) >= 0 or
            cv2.pointPolygonTest(cnt, (w_p - 5, h_p - 5), False) >= 0 or
            area > 0.85 * total_area
        )
        if is_background:
            continue

        # Approximate contour with a polygon
        epsilon = 0.005 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        
        coords = approx.reshape(-1, 2).tolist()
        if len(coords) < 3:
            continue

        try:
            poly = sg.Polygon(coords)
            if not poly.is_valid:
                poly = make_valid(poly)
            
            if poly.is_empty:
                continue

            # Unpack multipolygons if any resulted from validation
            if poly.geom_type == 'MultiPolygon':
                parts = list(poly.geoms)
            else:
                parts = [poly]

            for part in parts:
                if part.area < min_area_thresh:
                    continue

                # Compute geometric features
                # Aspect Ratio of bounding box
                x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
                aspect_ratio = max(w_c, h_c) / min(w_c, h_c) if min(w_c, h_c) > 0 else 1.0

                # Compactness (circularity)
                perimeter = cv2.arcLength(cnt, True)
                compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0.0

                # Solidity
                rect_area = w_c * h_c
                solidity = float(area) / rect_area if rect_area > 0 else 0.0

                # Compute Edge Density (ignoring boundary walls)
                # Create mask for current contour
                cnt_mask = np.zeros(img_resized.shape, dtype=np.uint8)
                # Convert coords back to numpy format for drawing
                contour_pts = np.array(part.exterior.coords, dtype=np.int32).reshape((-1, 1, 2))
                cv2.drawContours(cnt_mask, [contour_pts], -1, 255, -1)

                # Erode mask to isolate interior details away from walls
                kernel_erode = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
                inner_mask = cv2.erode(cnt_mask, kernel_erode)

                inner_area = cv2.countNonZero(inner_mask)
                edge_pixels = 0
                if inner_area > 0:
                    inner_edges = cv2.bitwise_and(edges, inner_mask)
                    edge_pixels = cv2.countNonZero(inner_edges)
                    edge_density = float(edge_pixels) / inner_area
                else:
                    edge_density = 0.0

                # Compute Parallelism Ratio inside the inner mask to identify parallel step lines (stairs)
                parallelism_ratio = 0.0
                if inner_area > 0 and edge_pixels > 0:
                    edge_x = sobelx[inner_edges > 0]
                    edge_y = sobely[inner_edges > 0]
                    magnitudes = np.sqrt(edge_x**2 + edge_y**2)
                    strong_grad = magnitudes > 20.0
                    
                    if np.sum(strong_grad) > 10:
                        edge_x = edge_x[strong_grad]
                        edge_y = edge_y[strong_grad]
                        angles = np.arctan2(edge_y, edge_x) * 180.0 / np.pi
                        angles = np.mod(angles + 180.0, 180.0)
                        
                        hist, bin_edges = np.histogram(angles, bins=18, range=(0, 180))
                        peak_idx = np.argmax(hist)
                        adjacent_sum = hist[peak_idx]
                        adjacent_sum += hist[(peak_idx - 1) % 18]
                        adjacent_sum += hist[(peak_idx + 1) % 18]
                        parallelism_ratio = adjacent_sum / len(angles)

                # CLASSIFICATION LOGIC
                element_type = "room"  # Default

                # 1. Sprawling Corridor check: very large area with branching/low-compactness
                if part.area > 20000.0 and compactness < 0.15:
                    element_type = "corridor"
                # 2. If high internal edges (furniture or stairs steps)
                elif edge_density >= 0.05:
                    # Stairs must have high parallelism, smaller area, and elongated aspect ratio
                    if parallelism_ratio > 0.65 and part.area < 10000.0 and aspect_ratio > 1.2:
                        element_type = "stairs"
                    else:
                        element_type = "room"
                # 3. Low internal edges (corridors, elevators, empty rooms)
                else:
                    if 800 <= part.area <= 8000 and aspect_ratio < 1.35 and solidity > 0.85 and edge_density > 0.02:
                        element_type = "elevator"
                    elif (aspect_ratio > 2.5 or compactness < 0.15) and part.area < 10000.0:
                        element_type = "corridor"
                    else:
                        element_type = "room"

                # Geometric refinement:
                # Rooms, stairs, and elevators MUST be represented as proper rectangles/squares (oriented bounding boxes)
                # to eliminate any jagged/awkward desk protrusions and columns along the walls.
                # Corridors keep their raw sprawling boundaries to flow around rooms.
                if element_type in ["room", "stairs", "elevator"]:
                    rect = cv2.minAreaRect(cnt)
                    box = cv2.boxPoints(rect)
                    
                    centroid_coord = (float(rect[0][0]) / scale, float(rect[0][1]) / scale)
                    ext_coords = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in box]
                    ext_coords.append(ext_coords[0]) # close polygon
                    part_area = float(rect[1][0] * rect[1][1]) / (scale ** 2)
                else:
                    centroid = part.centroid
                    centroid_coord = (float(centroid.x) / scale, float(centroid.y) / scale)
                    ext_coords = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in part.exterior.coords]
                    part_area = float(part.area) / (scale ** 2)

                geom_item = GeometryItem(
                    id=geom_id_counter,
                    type=element_type,
                    coordinates=ext_coords,
                    area=part_area,
                    centroid=centroid_coord
                )
                geometry_items.append(geom_item)
                poly_objects[geom_id_counter] = part
                geom_id_counter += 1

        except Exception:
            continue

    # STAGE 2: TOPOLOGY EXTRACTION (NetworkX)
    # Rooms are connected (adjacent) if their distance in the scaled space is below wall limit
    G = nx.Graph()

    # Populate nodes
    for item in geometry_items:
        G.add_node(
            item.id,
            centroid=item.centroid,
            area=item.area,
            type=item.type
        )

    # Compute adjacency based on scaled polygon distance
    adjacency_distance_threshold = 55.0  # pixels in scaled space

    for i in range(len(geometry_items)):
        id_i = geometry_items[i].id
        poly_i = poly_objects[id_i]
        centroid_i = geometry_items[i].centroid

        for j in range(i + 1, len(geometry_items)):
            id_j = geometry_items[j].id
            poly_j = poly_objects[id_j]
            centroid_j = geometry_items[j].centroid

            # Shapely calculates shortest distance between scaled polygons
            dist = float(poly_i.distance(poly_j))

            if dist < adjacency_distance_threshold:
                # Compute original centroid-to-centroid distance for topological edge
                c_dist = float(np.sqrt((centroid_i[0] - centroid_j[0])**2 + (centroid_i[1] - centroid_j[1])**2))
                G.add_edge(id_i, id_j, distance=c_dist)

    # Format output topology graph
    nodes_list = []
    edges_list = []

    for node_id, attrs in G.nodes(data=True):
        nodes_list.append(TopologyNode(
            id=node_id,
            type=attrs["type"],
            centroid=attrs["centroid"],
            area=attrs["area"]
        ))

    for u, v, attrs in G.edges(data=True):
        edges_list.append(TopologyEdge(
            source=u,
            target=v,
            distance=attrs["distance"]
        ))

    topology_graph = TopologyGraph(
        nodes=nodes_list,
        edges=edges_list
    )

    processing_time = (time.perf_counter() - start_time) * 1000.0

    return SpatialGraphResponse(
        processing_time_ms=processing_time,
        geometry=geometry_items,
        topology=topology_graph
    )
