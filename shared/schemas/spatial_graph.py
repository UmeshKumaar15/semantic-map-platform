from pydantic import BaseModel, Field
from typing import List, Tuple

class GeometryItem(BaseModel):
    id: int = Field(..., description="Unique ID for this geometry contour/polygon")
    type: str = Field("room", description="Type of geometry item (e.g., room, wall)")
    coordinates: List[List[float]] = Field(..., description="List of 2D coordinates [x, y] representing the polygon vertices")
    area: float = Field(..., description="Computed area of the polygon")
    centroid: Tuple[float, float] = Field(..., description="Centroid coordinate (x, y) of the polygon")

class TopologyNode(BaseModel):
    id: int = Field(..., description="Unique ID of the node corresponding to geometry ID")
    type: str = Field("room", description="Type of node")
    centroid: Tuple[float, float] = Field(..., description="Centroid coordinate (x, y)")
    area: float = Field(..., description="Area of the node room")

class TopologyEdge(BaseModel):
    source: int = Field(..., description="Source node ID")
    target: int = Field(..., description="Target node ID")
    distance: float = Field(..., description="Distance between room centroids")

class TopologyGraph(BaseModel):
    nodes: List[TopologyNode] = Field(..., description="List of nodes in the graph")
    edges: List[TopologyEdge] = Field(..., description="List of adjacency edges in the graph")

class SpatialGraphResponse(BaseModel):
    processing_time_ms: float = Field(..., description="Time taken to process the image in milliseconds")
    geometry: List[GeometryItem] = Field(..., description="Extracted geometry elements")
    topology: TopologyGraph = Field(..., description="Extracted room topology graph")
