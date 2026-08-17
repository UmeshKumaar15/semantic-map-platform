import sys
import numpy as np
import cv2
from pathlib import Path
import io
import asyncio
from fastapi import UploadFile

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import endpoint logic
from backend.src.api.v1.uploads import upload_floorplan

async def test_pipeline():
    print("Creating dummy floorplan image...")
    # Create a 400x400 image, background is white (255)
    img = np.ones((400, 400), dtype=np.uint8) * 255
    
    # Draw outer border (walls)
    cv2.rectangle(img, (0, 0), (399, 399), 0, 12)
    
    # Draw a divider wall down the middle (x=185 to x=215)
    # This splits the image into two rooms: Left Room and Right Room
    cv2.rectangle(img, (185, 0), (215, 399), 0, -1)

    # Draw mock desks/furniture as 16 SOLID filled black rectangles inside Left Room to boost edge density
    for y in range(50, 350, 40):
        cv2.rectangle(img, (40, y), (80, y + 20), 0, -1)
        cv2.rectangle(img, (100, y), (140, y + 20), 0, -1)

    # Draw mock desks/furniture inside Right Room
    for y in range(50, 350, 40):
        cv2.rectangle(img, (240, y), (280, y + 20), 0, -1)
        cv2.rectangle(img, (300, y), (340, y + 20), 0, -1)
    
    # Save dummy image to PNG bytes
    _, img_encoded = cv2.imencode('.png', img)
    img_bytes = img_encoded.tobytes()
    
    # Wrap in FastAPI UploadFile
    upload_file = UploadFile(
        file=io.BytesIO(img_bytes),
        filename="dummy_floorplan.png"
    )
    
    print("Running pipeline...")
    response = await upload_floorplan(upload_file)
    
    print("\n--- Pipeline Verification Results ---")
    print(f"Processing time: {response.processing_time_ms:.2f} ms")
    print(f"Detected geometry items (rooms): {len(response.geometry)}")
    for geom in response.geometry:
        print(f" - Element {geom.id} ({geom.type}): centroid={geom.centroid}, area={geom.area:.1f}")
        
    print(f"Topology nodes: {len(response.topology.nodes)}")
    print(f"Topology edges: {len(response.topology.edges)}")
    for edge in response.topology.edges:
        print(f" - Connection: Room {edge.source} <-> Room {edge.target} (distance={edge.distance:.1f}px)")
        
    # Assertions
    # We expect 2 rooms (one left of the middle divider, one right of it)
    assert len(response.geometry) == 2, f"Expected 2 elements, got {len(response.geometry)}"
    assert len(response.topology.nodes) == 2, f"Expected 2 nodes, got {len(response.topology.nodes)}"
    assert len(response.topology.edges) == 1, f"Expected 1 edge, got {len(response.topology.edges)}"
    
    # Verify both are classified as "room" due to furniture
    for geom in response.geometry:
        assert geom.type == "room", f"Expected element type 'room', got '{geom.type}'"

    print("\nSUCCESS: All pipeline verification checks passed!")

if __name__ == "__main__":
    asyncio.run(test_pipeline())
