'use client';
import React, { useEffect, useRef } from 'react';
import { getRiskVariant } from './RiskBadge';

interface Props {
  activeLayers?: string[];
  selectedStationId?: string;
  onSelect?: (id: string) => void;
  stations: any[];
  reservoirs?: any[];
}

export default function CauveryMap({
  activeLayers = ['stations', 'reservoirs'],
  selectedStationId,
  onSelect,
  stations = [],
  reservoirs = [],
}: Props) {
  const mapRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === 'undefined' || !containerRef.current) return;

    let isMounted = true;

    import('leaflet').then((L) => {
      if (!isMounted) return;

      if (!mapRef.current) {
        // Initialize Map
        const map = L.map(containerRef.current!, {
          center: [11.35, 78.1],
          zoom: 8,
          zoomControl: true,
          attributionControl: false,
        });
        mapRef.current = map;

        // Clean CartoDB Dark tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
          maxZoom: 18,
        }).addTo(map);

        // Approximate Cauvery main stem
        const riverCoords: [number, number][] = [
          [12.42, 75.57],
          [12.35, 76.0],
          [12.2, 76.4],
          [12.0, 76.8],
          [11.98, 77.0],
          [11.85, 77.4],
          [11.78, 77.8],
          [11.5, 78.1],
          [11.33, 77.72],
          [11.17, 77.87],
          [10.97, 78.07],
          [10.95, 78.43],
          [10.8, 78.7],
          [10.87, 79.1],
        ];

        L.polyline(riverCoords, {
          color: '#0284c7',
          weight: 3.5,
          opacity: 0.75,
        }).addTo(map);
      }

      const map = mapRef.current;

      // Clear existing markers before redrawing
      map.eachLayer((layer: any) => {
        if (layer instanceof L.Marker) {
          map.removeLayer(layer);
        }
      });

      // 1. Draw Gauging Stations
      if (activeLayers.includes('stations')) {
        stations.forEach((s) => {
          if (!s.lat || !s.lon || isNaN(s.lat) || isNaN(s.lon)) return;

          const isSelected = selectedStationId === s.id;
          const { color, label } = getRiskVariant(s.risk_level || 'Safe');

          const icon = L.divIcon({
            className: '',
            html: `
              <div style="
                width: ${isSelected ? 26 : 20}px;
                height: ${isSelected ? 26 : 20}px;
                border-radius: 50%;
                background: ${color};
                border: ${isSelected ? '3px solid #38bdf8' : '2px solid #ffffff'};
                box-shadow: ${isSelected ? '0 0 14px #38bdf8, 0 2px 8px rgba(0,0,0,0.6)' : '0 2px 6px rgba(0,0,0,0.5)'};
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s ease;
              ">
                <div style="width: ${isSelected ? 8 : 6}px; height: ${isSelected ? 8 : 6}px; border-radius: 50%; background: #080d1a;"></div>
              </div>`,
            iconSize: isSelected ? [26, 26] : [20, 20],
            iconAnchor: isSelected ? [13, 13] : [10, 10],
          });

          const marker = L.marker([s.lat, s.lon], { icon }).addTo(map);

          marker.bindPopup(`
            <div style="font-family: Inter, sans-serif; min-width: 190px; padding: 2px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <div style="font-weight: 700; font-size: 0.88rem; color: #f8fafc;">
                  ${s.name}
                </div>
                ${isSelected ? '<span style="font-size: 0.65rem; color: #38bdf8; background: rgba(14,165,233,0.18); padding: 1px 6px; border-radius: 4px; font-weight: 600;">ACTIVE</span>' : ''}
              </div>
              <div style="display: flex; justify-content: space-between; margin-bottom: 3px; font-size: 0.76rem;">
                <span style="color: #94a3b8;">Water Level:</span>
                <span style="color: #f8fafc; font-weight: 600; font-family: monospace;">
                  ${Number(s.water_level || 0).toFixed(2)} ft
                </span>
              </div>
              <div style="display: flex; justify-content: space-between; margin-bottom: 3px; font-size: 0.76rem;">
                <span style="color: #94a3b8;">Danger Level:</span>
                <span style="color: #ef4444; font-weight: 600; font-family: monospace;">
                  ${Number(s.danger_level || 0).toFixed(1)} ft
                </span>
              </div>
              <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 0.76rem;">
                <span style="color: #94a3b8;">Status:</span>
                <span style="color: ${color}; font-weight: 700; text-transform: uppercase; font-size: 0.72rem;">
                  ${label}
                </span>
              </div>
              <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.72rem; color: #38bdf8; text-align: center;">
                Click marker to view live hydrograph
              </div>
            </div>
          `);

          if (onSelect) {
            marker.on('click', () => onSelect(s.id));
          }
        });
      }

      // 2. Draw Reservoirs
      if (activeLayers.includes('reservoirs') && reservoirs && reservoirs.length > 0) {
        reservoirs.forEach((r) => {
          if (!r.lat || !r.lon || isNaN(r.lat) || isNaN(r.lon)) return;

          const isSelected = selectedStationId === r.id;
          const pct = r.storage_pct || 0;
          const color = pct > 85 ? '#ef4444' : pct > 70 ? '#f59e0b' : '#0ea5e9';

          const icon = L.divIcon({
            className: '',
            html: `
              <div style="
                width: ${isSelected ? 32 : 26}px;
                height: ${isSelected ? 32 : 26}px;
                border-radius: 4px;
                background: #0e1626;
                border: ${isSelected ? '3px solid #38bdf8' : `2px solid ${color}`};
                display: flex;
                align-items: center;
                justify-content: center;
                color: ${isSelected ? '#38bdf8' : color};
                font-size: ${isSelected ? 10 : 9}px;
                font-weight: 700;
                font-family: monospace;
                box-shadow: ${isSelected ? '0 0 14px #38bdf8, 0 2px 8px rgba(0,0,0,0.6)' : '0 2px 6px rgba(0,0,0,0.5)'};
                transition: all 0.2s ease;
              ">${Math.round(pct)}%</div>`,
            iconSize: isSelected ? [32, 32] : [26, 26],
            iconAnchor: isSelected ? [16, 16] : [13, 13],
          });

          const marker = L.marker([r.lat, r.lon], { icon }).addTo(map);

          marker.bindPopup(`
            <div style="font-family: Inter, sans-serif; min-width: 180px; padding: 2px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <strong style="color: #f8fafc; font-size: 0.86rem;">${r.name}</strong>
                ${isSelected ? '<span style="font-size: 0.65rem; color: #38bdf8; background: rgba(14,165,233,0.18); padding: 1px 6px; border-radius: 4px; font-weight: 600;">ACTIVE</span>' : ''}
              </div>
              <div style="display: flex; justify-content: space-between; margin-top: 6px; font-size: 0.76rem;">
                <span style="color: #94a3b8;">Storage:</span>
                <span style="color: ${color}; font-weight: 600;">${pct.toFixed(1)}%</span>
              </div>
              <div style="display: flex; justify-content: space-between; margin-top: 2px; font-size: 0.76rem;">
                <span style="color: #94a3b8;">Capacity:</span>
                <span style="color: #f8fafc; font-weight: 500;">${Number(r.capacity_mcft || 0).toLocaleString()} MCFT</span>
              </div>
              <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.72rem; color: #38bdf8; text-align: center;">
                Click reservoir to view live hydrograph
              </div>
            </div>
          `);

          if (onSelect) {
            marker.on('click', () => onSelect(r.id));
          }
        });
      }
    });

    return () => {
      isMounted = false;
    };
  }, [stations, reservoirs, activeLayers, onSelect, selectedStationId]);

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 380,
        borderRadius: 8,
        overflow: 'hidden',
        border: '1px solid var(--border-subtle)',
      }}
    />
  );
}
