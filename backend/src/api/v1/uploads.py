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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_SRC = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from shared.schemas.spatial_graph import (
    SpatialGraphResponse,
    GeometryItem,
    TopologyGraph,
    TopologyNode,
    TopologyEdge,
)
from services.floorplan_model import FloorplanMLService, CLASS_MAP

router = APIRouter()
ml_service = FloorplanMLService()

@router.post("/uploads", response_model=SpatialGraphResponse)
async def upload_floorplan(file: UploadFile = File(...)):
    filename = file.filename or ""
    if not (filename.lower().endswith('.png') or filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg')):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Only PNG, JPG, and JPEG images are allowed."
        )

    t0 = time.perf_counter()

    try:
        data = await file.read()
        nparr = np.frombuffer(data, np.uint8)
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

    h, w = img.shape
    max_dim = 1200.0
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_resized = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        img_resized = img.copy()

    # handle dark mode or negative floorplans dynamically
    min_val, max_val = float(img_resized.min()), float(img_resized.max())
    median_val = float(np.median(img_resized))
    midpoint = (min_val + max_val) / 2.0
    
    if median_val <= midpoint:
        img_resized = 255 - img_resized
        min_val, max_val = float(img_resized.min()), float(img_resized.max())

    # ML Inference Prediction Mask
    ml_pred_mask = ml_service.predict_mask(img_resized)

    # thresholding and binarization
    thresh_val = min_val + 0.85 * (max_val - min_val) if max_val - min_val > 1.0 else 220.0
    _, thresh_inv = cv2.threshold(img_resized, thresh_val, 255, cv2.THRESH_BINARY_INV)

    # remove noise, text, annotations and seal doorway gaps
    wall_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thick_walls = cv2.morphologyEx(thresh_inv, cv2.MORPH_OPEN, wall_kernel)
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    walls_dilated = cv2.dilate(thick_walls, kernel_dilate, iterations=2)

    spaces_thick = cv2.bitwise_not(walls_dilated)
    h_p, w_p = spaces_thick.shape

    # structural analysis / interior edges
    edges = cv2.Canny(img_resized, 50, 150)
    sobelx = cv2.Sobel(img_resized, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(img_resized, cv2.CV_64F, 0, 1, ksize=3)

    contours, hierarchy = cv2.findContours(spaces_thick, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    geometry_items: List[GeometryItem] = []
    poly_objects = {}
    
    min_area = 400.0
    max_area = 0.95 * h_p * w_p
    total_area = h_p * w_p
    geom_id = 1

    for i, cnt in enumerate(contours):
        if hierarchy is not None and hierarchy[0, i, 3] != -1:
            continue
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        # ignore border margins
        is_bg = (
            cv2.pointPolygonTest(cnt, (5, 5), False) >= 0 or
            cv2.pointPolygonTest(cnt, (w_p - 5, 5), False) >= 0 or
            cv2.pointPolygonTest(cnt, (5, h_p - 5), False) >= 0 or
            cv2.pointPolygonTest(cnt, (w_p - 5, h_p - 5), False) >= 0 or
            area > 0.85 * total_area
        )
        if is_bg:
            continue

        approx = cv2.approxPolyDP(cnt, 0.005 * cv2.arcLength(cnt, True), True)
        coords = approx.reshape(-1, 2).tolist()
        if len(coords) < 3:
            continue

        try:
            poly = sg.Polygon(coords)
            if not poly.is_valid:
                poly = make_valid(poly)
            
            if poly.is_empty:
                continue

            parts = list(poly.geoms) if poly.geom_type == 'MultiPolygon' else [poly]

            for part in parts:
                if part.area < min_area:
                    continue

                x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
                aspect_ratio = max(w_c, h_c) / min(w_c, h_c) if min(w_c, h_c) > 0 else 1.0
                compactness = (4 * np.pi * area) / (cv2.arcLength(cnt, True) ** 2) if cv2.arcLength(cnt, True) > 0 else 0.0
                solidity = float(area) / (w_c * h_c) if w_c * h_c > 0 else 0.0

                # edge density computation
                cnt_mask = np.zeros(img_resized.shape, dtype=np.uint8)
                contour_pts = np.array(part.exterior.coords, dtype=np.int32).reshape((-1, 1, 2))
                cv2.drawContours(cnt_mask, [contour_pts], -1, 255, -1)
                
                inner_mask = cv2.erode(cnt_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
                inner_area = cv2.countNonZero(inner_mask)
                edge_pixels = 0
                if inner_area > 0:
                    inner_edges = cv2.bitwise_and(edges, inner_mask)
                    edge_pixels = cv2.countNonZero(inner_edges)
                    edge_density = float(edge_pixels) / inner_area
                else:
                    edge_density = 0.0

                # line direction parallelism (for stairs detection)
                parallelism = 0.0
                if inner_area > 0 and edge_pixels > 0:
                    ex = sobelx[inner_edges > 0]
                    ey = sobely[inner_edges > 0]
                    mags = np.sqrt(ex**2 + ey**2)
                    strong = mags > 20.0
                    
                    if np.sum(strong) > 10:
                        angles = np.mod(np.arctan2(ey[strong], ex[strong]) * 180.0 / np.pi + 180.0, 180.0)
                        hist, _ = np.histogram(angles, bins=18, range=(0, 180))
                        peak = np.argmax(hist)
                        parallelism = (hist[peak] + hist[(peak-1)%18] + hist[(peak+1)%18]) / len(angles)

                # Check if ML model mask predicts a clear class inside inner_mask
                ml_class_id = 0
                if inner_area > 0 and np.any(ml_pred_mask):
                    crop_ml = ml_pred_mask[inner_mask > 0]
                    counts = np.bincount(crop_ml)
                    if len(counts) > 1 and np.max(counts[1:]) > 0.4 * len(crop_ml):
                        ml_class_id = np.argmax(counts[1:]) + 1

                # Space Classification (Hybrid ML + Heuristics)
                if ml_class_id in CLASS_MAP:
                    room_type = CLASS_MAP[ml_class_id]
                else:
                    if part.area > 20000.0 and compactness < 0.15:
                        room_type = "corridor"
                    elif edge_density >= 0.05:
                        if parallelism > 0.65 and part.area < 10000.0 and aspect_ratio > 1.2:
                            room_type = "stairs"
                        else:
                            room_type = "room"
                    else:
                        if 800 <= part.area <= 8000 and aspect_ratio < 1.35 and solidity > 0.85 and edge_density > 0.02:
                            room_type = "elevator"
                        elif (aspect_ratio > 2.5 or compactness < 0.15) and part.area < 10000.0:
                            room_type = "corridor"
                        else:
                            room_type = "room"

                # Geometry refinement
                if room_type in ["room", "stairs", "elevator"]:
                    rect = cv2.minAreaRect(cnt)
                    box = cv2.boxPoints(rect)
                    centroid_coord = (float(rect[0][0]) / scale, float(rect[0][1]) / scale)
                    ext_coords = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in box]
                    ext_coords.append(ext_coords[0])
                    part_area = float(rect[1][0] * rect[1][1]) / (scale ** 2)
                else:
                    centroid = part.centroid
                    centroid_coord = (float(centroid.x) / scale, float(centroid.y) / scale)
                    ext_coords = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in part.exterior.coords]
                    part_area = float(part.area) / (scale ** 2)

                geometry_items.append(GeometryItem(
                    id=geom_id,
                    type=room_type,
                    coordinates=ext_coords,
                    area=part_area,
                    centroid=centroid_coord
                ))
                poly_objects[geom_id] = part
                geom_id += 1

        except Exception:
            continue

    # Topology Graph Extraction
    G = nx.Graph()

    for item in geometry_items:
        G.add_node(item.id, centroid=item.centroid, area=item.area, type=item.type)

    for i in range(len(geometry_items)):
        id_i = geometry_items[i].id
        poly_i = poly_objects[id_i]
        c_i = geometry_items[i].centroid

        for j in range(i + 1, len(geometry_items)):
            id_j = geometry_items[j].id
            poly_j = poly_objects[id_j]
            c_j = geometry_items[j].centroid

            if float(poly_i.distance(poly_j)) < 55.0:
                c_dist = float(np.sqrt((c_i[0] - c_j[0])**2 + (c_i[1] - c_j[1])**2))
                G.add_edge(id_i, id_j, distance=c_dist)

    nodes = [TopologyNode(id=nid, type=attrs["type"], centroid=attrs["centroid"], area=attrs["area"]) for nid, attrs in G.nodes(data=True)]
    edges = [TopologyEdge(source=u, target=v, distance=attrs["distance"]) for u, v, attrs in G.edges(data=True)]

    return SpatialGraphResponse(
        processing_time_ms=(time.perf_counter() - t0) * 1000.0,
        geometry=geometry_items,
        topology=TopologyGraph(nodes=nodes, edges=edges)
    )
