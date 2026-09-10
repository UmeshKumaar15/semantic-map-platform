'use client';

import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { 
  Upload, FileImage, Cpu, Layers, Activity, 
  FileText, Copy, Check, RotateCcw, AlertCircle, 
  ZoomIn, Eye, Sparkles, Download
} from 'lucide-react';

interface GeometryItem {
  id: number;
  type: string;
  coordinates: [number, number][];
  area: number;
  centroid: [number, number];
}

interface TopologyNode {
  id: number;
  type: string;
  centroid: [number, number];
  area: number;
}

interface TopologyEdge {
  source: number;
  target: number;
  distance: number;
}

interface TopologyGraph {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

interface SpatialGraphResponse {
  processing_time_ms: number;
  geometry: GeometryItem[];
  topology: TopologyGraph;
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [responseData, setResponseData] = useState<SpatialGraphResponse | null>(null);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [hoveredRoomId, setHoveredRoomId] = useState<number | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [showRawJSON, setShowRawJSON] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Clean up Object URL
  useEffect(() => {
    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl);
      }
    };
  }, [imageUrl]);

  const handleFileChange = (selectedFile: File) => {
    if (!selectedFile) return;
    
    // Check type
    if (!selectedFile.type.startsWith('image/')) {
      setError('Invalid file type. Please upload a PNG or JPG floorplan.');
      return;
    }

    setFile(selectedFile);
    setError(null);
    setResponseData(null);
    setHoveredRoomId(null);
    setSelectedRoomId(null);

    const url = URL.createObjectURL(selectedFile);
    setImageUrl(url);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const uploadAndProcess = async () => {
    if (!file) return;

    setIsProcessing(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'https://semantic-map-platform.onrender.com').replace(/\/$/, '');
      const response = await axios.post<SpatialGraphResponse>(
        `${apiBase}/api/v1/uploads`, 
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );
      setResponseData(response.data);
    } catch (err: any) {
      console.error(err);
      const targetUrl = (process.env.NEXT_PUBLIC_API_URL || 'https://semantic-map-platform.onrender.com').replace(/\/$/, '');
      setError(
        err.response?.data?.detail || 
        `Could not connect to map processing service at ${targetUrl}. (If server was sleeping on Render, please wait 30 seconds and try again).`
      );
    } finally {
      setIsProcessing(false);
    }
  };

  const copyToClipboard = () => {
    if (!responseData) return;
    navigator.clipboard.writeText(JSON.stringify(responseData, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadSVG = () => {
    if (!svgRef.current) return;
    try {
      const svgElement = svgRef.current;
      const serializer = new XMLSerializer();
      let source = serializer.serializeToString(svgElement);
      
      // Ensure xmlns is present
      if (!source.match(/^<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/)) {
        source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
      }
      
      // Add XML declaration
      source = '<?xml version="1.0" encoding="utf-8"?>\n' + source;

      const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      
      const link = document.createElement('a');
      link.href = url;
      link.download = `aethermap_spatial_graph_${file ? file.name.split('.')[0] : 'export'}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export SVG:', err);
    }
  };

  const resetAll = () => {
    setFile(null);
    setImageUrl(null);
    setResponseData(null);
    setError(null);
    setImageSize(null);
    setHoveredRoomId(null);
    setSelectedRoomId(null);
  };

  // Generate color palette based on room type
  const getRoomColor = (type: string, id: number, isHovered: boolean, isSelected: boolean) => {
    let hue = 210; // Default blue-gray for rooms
    let sat = 50;
    let light = 60;

    if (type === 'corridor') {
      hue = 45; // Muted orange/amber for corridors
      sat = 55;
      light = 65;
    } else if (type === 'elevator') {
      hue = 0; // Muted red for elevators
      sat = 50;
      light = 65;
    } else if (type === 'stairs') {
      hue = 280; // Muted purple for stairs
      sat = 45;
      light = 65;
    } else { // room
      hue = 200 + ((id * 37) % 30);
      sat = 50;
      light = 60;
    }

    if (isSelected) {
      return {
        fill: `hsla(${hue}, ${sat + 20}%, ${light - 15}%, 0.35)`,
        stroke: `hsla(${hue}, ${sat + 30}%, ${light - 25}%, 1)`,
        strokeWidth: 3
      };
    }
    if (isHovered) {
      return {
        fill: `hsla(${hue}, ${sat + 10}%, ${light - 5}%, 0.25)`,
        stroke: `hsla(${hue}, ${sat + 20}%, ${light - 15}%, 0.95)`,
        strokeWidth: 2.5
      };
    }
    return {
      fill: `hsla(${hue}, ${sat}%, ${light}%, 0.15)`,
      stroke: `hsla(${hue}, ${sat + 10}%, ${light - 10}%, 0.6)`,
      strokeWidth: 1.5
    };
  };

  return (
    <main className="min-h-screen bg-slate-50 text-slate-800 font-sans pb-16">
      {/* Top Banner Header - Plain & Functional */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Cpu className="h-5 w-5 text-slate-700" />
            <div>
              <span className="text-lg font-bold tracking-tight text-slate-900">AetherMap</span>
              <span className="ml-2 text-xs text-slate-400 font-mono">v0.1.0-prototype</span>
            </div>
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            <span>Bare-Metal Dev Mode</span>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 mt-8">
        {/* Simple Page Intro */}
        <div className="mb-8 border-b border-slate-200 pb-6">
          <h2 className="text-2xl font-bold text-slate-950">Floorplan Spatial Parser</h2>
          <p className="mt-1 text-slate-500 text-sm">
            Upload floorplan drawings (PNG/JPG) to parse rooms, corridors, stairs, and elevators into spatial graph coordinates using a local geometry pipeline.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-start gap-2.5">
            <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Error running pipeline:</span>
              <p className="mt-0.5 text-red-600/90">{error}</p>
            </div>
          </div>
        )}

        {/* 2-Column Wireframe Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* LEFT: Controls & Setup */}
          <div className="lg:col-span-4 space-y-6">
            
            {/* INGESTION BOX */}
            <div className="bg-white border border-slate-200 rounded-md p-5 shadow-sm">
              <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
                <FileImage className="h-4 w-4 text-slate-500" /> 1. Upload Floorplan
              </h3>

              {!imageUrl ? (
                <div 
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  onClick={triggerFileInput}
                  className="border border-dashed border-slate-300 bg-slate-50 hover:bg-slate-100/60 rounded p-6 text-center cursor-pointer transition-colors"
                >
                  <input 
                    type="file" 
                    ref={fileInputRef} 
                    className="hidden" 
                    accept="image/png, image/jpeg, image/jpg"
                    onChange={(e) => e.target.files && handleFileChange(e.target.files[0])}
                  />
                  <Upload className="h-6 w-6 text-slate-400 mx-auto mb-2" />
                  <p className="text-xs font-semibold text-slate-700">Click or Drag Image Here</p>
                  <p className="text-[10px] text-slate-400 mt-1">Supports PNG or JPG files</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="relative border border-slate-200 rounded bg-slate-100 aspect-video flex items-center justify-center overflow-hidden">
                    <img 
                      src={imageUrl} 
                      alt="Upload Preview" 
                      className="max-w-full max-h-full object-contain"
                    />
                  </div>

                  <div className="p-3 bg-slate-50 border border-slate-200 rounded text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-slate-500">File:</span>
                      <span className="font-mono text-slate-700 truncate max-w-[180px]">{file?.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Size:</span>
                      <span className="font-mono text-slate-700">{file ? `${(file.size / 1024).toFixed(1)} KB` : '0 KB'}</span>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={resetAll}
                      className="flex-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 font-semibold py-1.5 px-3 rounded text-xs transition-colors flex items-center justify-center gap-1"
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> Clear
                    </button>
                    
                    {!responseData && (
                      <button
                        onClick={uploadAndProcess}
                        disabled={isProcessing}
                        className="flex-[2] bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 text-white font-semibold py-1.5 px-3 rounded text-xs transition-colors flex items-center justify-center gap-1.5 shadow-sm"
                      >
                        {isProcessing ? (
                          <>
                            <span className="h-3 w-3 border-2 border-slate-400 border-t-slate-800 rounded-full animate-spin inline-block" />
                            <span>Processing...</span>
                          </>
                        ) : (
                          <>
                            <Activity className="h-3.5 w-3.5" />
                            <span>Run Inferences</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* PROCESS EXPLANATION */}
            <div className="bg-white border border-slate-200 rounded-md p-5 shadow-sm">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">Pipeline Math</h3>
              <ol className="text-xs text-slate-600 space-y-2.5 list-decimal pl-4">
                <li>
                  <span className="font-bold text-slate-800">Dynamic Normalization</span>: Scale dimensions to 1200px and auto-invert if dark-mode.
                </li>
                <li>
                  <span className="font-bold text-slate-800">Binarization & Closing</span>: Thick wall structures are dilated to seal doorways and windows.
                </li>
                <li>
                  <span className="font-bold text-slate-800">Interior Gradient Audit</span>: Calculate line directionality (parallelism) inside spaces.
                </li>
                <li>
                  <span className="font-bold text-slate-800">Topology Generation</span>: Check adjacent room boundaries and write edges.
                </li>
              </ol>
            </div>
          </div>

          {/* RIGHT: Visual Canvas & Inspector Panels */}
          <div className="lg:col-span-8 space-y-6">
            
            {/* INTERACTIVE CANVAS */}
            <div className="bg-white border border-slate-200 rounded-md p-5 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3 mb-4">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Layers className="h-4 w-4 text-slate-500" /> 2. Visual Layout Overlay
                </h3>
                
                {responseData && (
                  <button
                    onClick={downloadSVG}
                    className="px-2 py-1 bg-green-50 border border-green-200 text-green-700 hover:bg-green-100 rounded text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 transition-colors"
                  >
                    <Download className="h-3 w-3" /> Export SVG
                  </button>
                )}
              </div>

              {!responseData ? (
                <div className="h-[380px] rounded border border-dashed border-slate-200 bg-slate-50 flex flex-col items-center justify-center text-slate-400 text-center p-6">
                  <Eye className="h-8 w-8 text-slate-300 mb-2" />
                  <p className="text-xs font-bold text-slate-600">No layout output loaded</p>
                  <p className="text-[11px] max-w-xs mt-1 text-slate-400">Please upload a floorplan drawing and click "Run Inferences" to see semantic boundaries and adjacency graph lines.</p>
                </div>
              ) : (
                <div className="relative border border-slate-200 rounded bg-slate-100 flex items-center justify-center overflow-hidden max-h-[500px]">
                  {imageUrl && (
                    <>
                      <img 
                        src={imageUrl} 
                        alt="Blueprint source background" 
                        className="max-w-full max-h-[500px] object-contain block opacity-30 select-none pointer-events-none"
                        onLoad={(e) => {
                          const img = e.currentTarget;
                          setImageSize({ width: img.naturalWidth, height: img.naturalHeight });
                        }}
                      />
                      {imageSize && (
                        <svg
                          ref={svgRef}
                          viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
                          className="absolute inset-0 w-full h-full"
                          style={{ pointerEvents: 'none' }}
                        >
                          {/* Polygons (Geometry) */}
                          {responseData.geometry.map((geom) => {
                            const isHovered = hoveredRoomId === geom.id;
                            const isSelected = selectedRoomId === geom.id;
                            const colors = getRoomColor(geom.type, geom.id, isHovered, isSelected);

                            return (
                              <polygon
                                key={`room-${geom.id}`}
                                points={geom.coordinates.map((c) => `${c[0]},${c[1]}`).join(' ')}
                                fill={colors.fill}
                                stroke={colors.stroke}
                                strokeWidth={colors.strokeWidth}
                                className="transition-all duration-150 cursor-pointer"
                                style={{ pointerEvents: 'auto' }}
                                onMouseEnter={() => setHoveredRoomId(geom.id)}
                                onMouseLeave={() => setHoveredRoomId(null)}
                                onClick={() => setSelectedRoomId(selectedRoomId === geom.id ? null : geom.id)}
                              />
                            );
                          })}

                          {/* Adjacency Graph Lines */}
                          {responseData.topology.edges.map((edge, index) => {
                            const srcNode = responseData.topology.nodes.find(n => n.id === edge.source);
                            const tgtNode = responseData.topology.nodes.find(n => n.id === edge.target);

                            if (!srcNode || !tgtNode) return null;

                            const isEdgeHighlighted = 
                              hoveredRoomId === edge.source || 
                              hoveredRoomId === edge.target || 
                              selectedRoomId === edge.source || 
                              selectedRoomId === edge.target;

                            return (
                              <line
                                key={`edge-${index}`}
                                x1={srcNode.centroid[0]}
                                y1={srcNode.centroid[1]}
                                x2={tgtNode.centroid[0]}
                                y2={tgtNode.centroid[1]}
                                stroke={isEdgeHighlighted ? "#22c55e" : "#8b5cf6"}
                                strokeWidth={isEdgeHighlighted ? 3 : 1.5}
                                strokeDasharray={isEdgeHighlighted ? "none" : "4,4"}
                              />
                            );
                          })}

                          {/* Graph Nodes (Centroids) */}
                          {responseData.topology.nodes.map((node) => {
                            const isHovered = hoveredRoomId === node.id;
                            const isSelected = selectedRoomId === node.id;
                            
                            return (
                              <g 
                                key={`node-${node.id}`}
                                style={{ pointerEvents: 'auto' }}
                                onMouseEnter={() => setHoveredRoomId(node.id)}
                                onMouseLeave={() => setHoveredRoomId(null)}
                                onClick={() => setSelectedRoomId(selectedRoomId === node.id ? null : node.id)}
                                className="cursor-pointer"
                              >
                                <circle
                                  cx={node.centroid[0]}
                                  cy={node.centroid[1]}
                                  r={isHovered || isSelected ? 7 : 4}
                                  fill={isHovered || isSelected ? "#22c55e" : "#8b5cf6"}
                                  stroke="#ffffff"
                                  strokeWidth={1}
                                />
                                <text
                                  x={node.centroid[0]}
                                  y={node.centroid[1] - 8}
                                  fill={isHovered || isSelected ? "#15803d" : "#4b5563"}
                                  fontSize={isHovered || isSelected ? "11" : "8"}
                                  fontWeight="bold"
                                  textAnchor="middle"
                                  style={{ userSelect: 'none' }}
                                >
                                  {node.type === 'room' ? `Room ${node.id}` : `${node.type.charAt(0).toUpperCase() + node.type.slice(1)} ${node.id}`}
                                </text>
                              </g>
                            );
                          })}
                        </svg>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* RESULTS METRICS & ANALYSIS PANELS */}
            {responseData && (
              <div className="space-y-6">
                
                {/* Stats Table Grid */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-white border border-slate-200 rounded p-4 shadow-sm">
                    <p className="text-[10px] uppercase font-bold text-slate-400">Processing Time</p>
                    <h4 className="text-xl font-bold text-slate-800 mt-0.5">
                      {responseData.processing_time_ms.toFixed(1)} ms
                    </h4>
                  </div>
                  <div className="bg-white border border-slate-200 rounded p-4 shadow-sm">
                    <p className="text-[10px] uppercase font-bold text-slate-400">Extracted Spaces</p>
                    <h4 className="text-xl font-bold text-slate-800 mt-0.5">
                      {responseData.geometry.length}
                    </h4>
                  </div>
                  <div className="bg-white border border-slate-200 rounded p-4 shadow-sm">
                    <p className="text-[10px] uppercase font-bold text-slate-400">Graph Adjacencies</p>
                    <h4 className="text-xl font-bold text-slate-800 mt-0.5">
                      {responseData.topology.edges.length}
                    </h4>
                  </div>
                </div>

                {/* Sub-counts row */}
                <div className="bg-slate-100 border border-slate-200 rounded p-3 text-xs flex flex-wrap gap-4 font-mono text-slate-600">
                  <span>Rooms: {responseData.geometry.filter(g => g.type === 'room').length}</span>
                  <span>Corridors: {responseData.geometry.filter(g => g.type === 'corridor').length}</span>
                  <span>Elevators: {responseData.geometry.filter(g => g.type === 'elevator').length}</span>
                  <span>Stairs: {responseData.geometry.filter(g => g.type === 'stairs').length}</span>
                </div>

                {/* Lists Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  
                  {/* Space element registry */}
                  <div className="bg-white border border-slate-200 rounded p-4 shadow-sm space-y-3">
                    <h4 className="text-xs font-bold text-slate-900 border-b border-slate-100 pb-2 flex justify-between">
                      <span>Spatial Directory</span>
                      <span className="text-[10px] text-slate-500 font-mono">{responseData.geometry.length} items</span>
                    </h4>
                    <div className="space-y-1.5 max-h-[220px] overflow-y-auto custom-scrollbar">
                      {responseData.geometry.map((room) => {
                        const isHovered = hoveredRoomId === room.id;
                        const isSelected = selectedRoomId === room.id;
                        return (
                          <div
                            key={`room-item-${room.id}`}
                            className={`p-2 rounded text-[11px] flex justify-between items-center cursor-pointer transition-colors border ${
                              isSelected 
                                ? 'bg-blue-50 border-blue-200 text-blue-800' 
                                : isHovered 
                                ? 'bg-slate-100 border-slate-300 text-slate-800' 
                                : 'bg-slate-50 border-slate-200 text-slate-600'
                            }`}
                            onMouseEnter={() => setHoveredRoomId(room.id)}
                            onMouseLeave={() => setHoveredRoomId(null)}
                            onClick={() => setSelectedRoomId(selectedRoomId === room.id ? null : room.id)}
                          >
                            <div className="font-semibold flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: getRoomColor(room.type, room.id, false, true).stroke }} />
                              <span>Element {room.id}</span>
                              <span className="text-[9px] uppercase tracking-wider bg-slate-200 text-slate-600 px-1 rounded font-normal font-mono">{room.type}</span>
                            </div>
                            <span className="font-mono text-[10px] text-slate-500">{(room.area).toFixed(0)} px²</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Adjacency Matrix Edges */}
                  <div className="bg-white border border-slate-200 rounded p-4 shadow-sm space-y-3">
                    <h4 className="text-xs font-bold text-slate-900 border-b border-slate-100 pb-2 flex justify-between">
                      <span>Adjacency Relations</span>
                      <span className="text-[10px] text-slate-500 font-mono">{responseData.topology.edges.length} edges</span>
                    </h4>
                    <div className="space-y-1.5 max-h-[220px] overflow-y-auto custom-scrollbar">
                      {responseData.topology.edges.length === 0 ? (
                        <p className="text-[10px] text-slate-400 py-6 text-center">No topological boundaries share proximity.</p>
                      ) : (
                        responseData.topology.edges.map((edge, index) => {
                          const isEdgeSelected = selectedRoomId === edge.source || selectedRoomId === edge.target;
                          const isEdgeHovered = hoveredRoomId === edge.source || hoveredRoomId === edge.target;
                          
                          return (
                            <div
                              key={`edge-item-${index}`}
                              className={`p-2 rounded text-[11px] flex justify-between items-center transition-colors border ${
                                isEdgeSelected
                                  ? 'bg-green-50 border-green-200 text-green-800'
                                  : isEdgeHovered
                                  ? 'bg-slate-150 border-slate-350 text-slate-700'
                                  : 'bg-slate-50 border-slate-200 text-slate-500'
                              }`}
                            >
                              <span>Space {edge.source} &harr; Space {edge.target}</span>
                              <span className="font-mono text-[10px] text-slate-400">{edge.distance.toFixed(0)} px</span>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                </div>

                {/* Raw JSON Inspector */}
                <div className="border border-slate-200 rounded overflow-hidden">
                  <button 
                    onClick={() => setShowRawJSON(!showRawJSON)}
                    className="w-full px-4 py-2 flex items-center justify-between bg-slate-100 hover:bg-slate-200/60 text-xs font-bold text-slate-700 border-b border-slate-200 transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-slate-500" /> 3. Raw Spatial Graph Output (JSON)
                    </span>
                    <span className="text-[10px] text-blue-600 font-semibold">{showRawJSON ? 'Hide' : 'Show'}</span>
                  </button>
                  {showRawJSON && (
                    <div className="relative">
                      <div className="absolute top-2 right-2">
                        <button
                          onClick={copyToClipboard}
                          className="px-2 py-1 bg-white hover:bg-slate-50 border border-slate-200 rounded text-[10px] flex items-center gap-1 font-semibold text-slate-600 transition-colors"
                        >
                          {copied ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
                          <span>{copied ? 'Copied' : 'Copy Data'}</span>
                        </button>
                      </div>
                      <pre className="p-4 text-[10px] font-mono text-slate-700 overflow-x-auto max-h-[260px] overflow-y-auto bg-slate-50 custom-scrollbar leading-relaxed">
                        <code>{JSON.stringify(responseData, null, 2)}</code>
                      </pre>
                    </div>
                  )}
                </div>

              </div>
            )}

          </div>
        </div>

      </div>

      {/* Simple Custom Scrollbar Style */}
      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 5px;
          height: 5px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: #f1f5f9;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 2px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>
    </main>
  );
}
