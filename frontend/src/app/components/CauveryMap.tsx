'use client';
import { useEffect, useRef } from 'react';
import { STATUS_CONFIG, type Status } from '../data/mockData';

interface Props {
  activeLayers: string[];
  onSelect: (id: string) => void;
  stations: any[];
  reservoirs: any[];
  alerts?: any[];
}

export default function CauveryMap({ activeLayers, onSelect, stations, reservoirs }: Props) {
  const mapRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    import('leaflet').then(L => {
      if (mapRef.current) {
        // Map is already initialized, but props changed (activeLayers, stations, reservoirs).
        // Let's clear previous markers and redraw to reflect current state conformed.
        const map = mapRef.current;
        map.eachLayer((layer: any) => {
          if (layer instanceof L.Marker || (layer instanceof L.Polyline && layer.options.color !== '#22d3ee' && layer.options.color !== '#67e8f9')) {
            map.removeLayer(layer);
          }
        });

        // Redraw Station markers
        if (activeLayers.includes('stations')) {
          stations.forEach(s => {
            const rawStatus = (s.risk_level || 'Safe').toLowerCase();
            const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
            const sc = STATUS_CONFIG[severity as Status] || STATUS_CONFIG.safe;
            
            const icon = L.divIcon({
              className: '',
              html: `
                <div style="
                  width:24px; height:24px; border-radius:50%;
                  background:${sc.color}25;
                  border:2px solid ${sc.color};
                  box-shadow: 0 0 16px ${sc.color}60, 0 0 32px ${sc.color}30;
                  display:flex; align-items:center; justify-content:center;
                  animation: pulse-${severity} 2s ease infinite;
                  position:relative;
                ">
                  <div style="
                    width:8px; height:8px; border-radius:50%;
                    background:${sc.color};
                  "></div>
                </div>`,
              iconSize: [24, 24],
              iconAnchor: [12, 12],
            });

            const marker = L.marker([s.lat, s.lon], { icon }).addTo(map);
            marker.bindPopup(`
              <div style="font-family:Inter,sans-serif; min-width:200px;">
                <div style="font-weight:700; font-size:0.9rem; color:#e2e8f0; margin-bottom:8px;">${s.name}</div>
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                  <span style="color:rgba(255,255,255,0.5); font-size:0.75rem;">Water Level</span>
                  <span style="color:${sc.color}; font-weight:600; font-family:monospace;">${s.water_level.toFixed(2)}ft / ${s.danger_level.toFixed(1)}ft</span>
                </div>
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                  <span style="color:rgba(255,255,255,0.5); font-size:0.75rem;">Discharge</span>
                  <span style="color:#22d3ee; font-weight:600;">${s.discharge.toFixed(1)} m³/s</span>
                </div>
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                  <span style="color:rgba(255,255,255,0.5); font-size:0.75rem;">Status</span>
                  <span style="color:${sc.color}; font-weight:600; text-transform:uppercase; font-size:0.72rem;">${sc.label}</span>
                </div>
                <div style="background:rgba(255,255,255,0.06); border-radius:4px; overflow:hidden; height:4px;">
                  <div style="height:100%; width:${Math.min(100, (s.water_level/s.danger_level*100)).toFixed(0)}%; background:${sc.color}; border-radius:4px;"></div>
                </div>
              </div>
            `, { className: '' });

            marker.on('click', () => onSelect(s.id));
          });
        }

        // Redraw Reservoir markers
        if (activeLayers.includes('reservoirs')) {
          reservoirs.forEach(r => {
            const pct = r.storage_pct;
            const color = pct > 90 ? '#fb7185' : pct > 75 ? '#fb923c' : '#22d3ee';
            const icon = L.divIcon({
              className: '',
              html: `<div style="
                width:32px; height:32px; border-radius:6px;
                background:${color}20; border:2px solid ${color};
                box-shadow:0 0 16px ${color}50;
                display:flex; align-items:center; justify-content:center;
                color:${color}; font-size:9px; font-weight:700; font-family:monospace;
              ">${pct.toFixed(0)}%</div>`,
              iconSize: [32, 32],
              iconAnchor: [16, 16],
            });
            L.marker([r.lat, r.lon], { icon }).addTo(map)
              .bindPopup(`<div style="font-family:Inter,sans-serif; min-width:180px;">
                <strong style="color:#e2e8f0; font-size:0.88rem;">${r.name}</strong><br/>
                <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:0.75rem;">
                  <span style="color:rgba(255,255,255,0.5)">Storage pct:</span>
                  <span style="color:${color}; font-weight:600;">${pct.toFixed(1)}%</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-top:2px;">
                  <span style="color:rgba(255,255,255,0.5)">Volume:</span>
                  <span style="color:${color}; font-weight:600;">${r.current_storage_mcft.toFixed(0)} MCFT</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-top:2px;">
                  <span style="color:rgba(255,255,255,0.5)">Spillway flow:</span>
                  <span style="color:#fb7185; font-weight:600;">${r.release_cumecs.toFixed(1)} m³/s</span>
                </div>
              </div>`);
          });
        }
        return;
      }

      // Initialize Map
      const map = L.map(containerRef.current!, {
        center: [11.3, 78.2], // Centered around central Tamil Nadu river path confluences
        zoom: 8,
        zoomControl: true,
        attributionControl: false,
      });
      mapRef.current = map;

      // Dark tile layer
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 18,
      }).addTo(map);

      // River path (approximate Cauvery main stem)
      const riverCoords: [number, number][] = [
        [12.42, 75.57], [12.35, 76.0], [12.2, 76.4], [12.0, 76.8],
        [11.98, 77.0], [11.85, 77.4], [11.78, 77.8], [11.5, 78.1],
        [11.33, 77.72], [11.17, 77.87], [10.97, 78.07], [10.95, 78.43],
        [10.80, 78.70], [10.87, 79.10],
      ];

      // Animate river with dashed polyline
      L.polyline(riverCoords, {
        color: '#22d3ee',
        weight: 3,
        opacity: 0.7,
        dashArray: '12, 8',
      }).addTo(map);

      // Animated river flow (secondary lighter line)
      L.polyline(riverCoords, { color: '#67e8f9', weight: 1, opacity: 0.3 }).addTo(map);

      // Render Stations & Reservoirs
      if (activeLayers.includes('stations')) {
        stations.forEach(s => {
          if (s.lat === undefined || s.lon === undefined || isNaN(s.lat) || isNaN(s.lon)) {
            console.warn(`Station ${s.name || s.id} has missing or invalid coordinates: lat=${s.lat}, lon=${s.lon}`);
            return;
          }
          const rawStatus = (s.risk_level || 'Safe').toLowerCase();
          const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
          const sc = STATUS_CONFIG[severity as Status] || STATUS_CONFIG.safe;
          
          const icon = L.divIcon({
            className: '',
            html: `
              <div style="
                width:24px; height:24px; border-radius:50%;
                background:${sc.color}25;
                border:2px solid ${sc.color};
                box-shadow: 0 0 16px ${sc.color}60, 0 0 32px ${sc.color}30;
                display:flex; align-items:center; justify-content:center;
                animation: pulse-${severity} 2s ease infinite;
                position:relative;
              ">
                <div style="
                  width:8px; height:8px; border-radius:50%;
                  background:${sc.color};
                "></div>
              </div>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
          });

          const marker = L.marker([s.lat, s.lon], { icon }).addTo(map);
          marker.bindPopup(`
            <div style="font-family:Inter,sans-serif; min-width:200px;">
              <div style="font-weight:700; font-size:0.9rem; color:#e2e8f0; margin-bottom:8px;">${s.name}</div>
              <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span style="color:rgba(255,255,255,0.5); font-size:0.75rem;">Water Level</span>
                <span style="color:${sc.color}; font-weight:600; font-family:monospace;">${s.water_level.toFixed(2)}ft / ${s.danger_level.toFixed(1)}ft</span>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span style="color:rgba(255,255,255,0.5); font-size:0.75rem;">Discharge</span>
                <span style="color:#22d3ee; font-weight:600;">${s.discharge.toFixed(1)} m³/s</span>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:rgba(255,255,255,0.5); font-size:0.75rem;">Status</span>
                <span style="color:${sc.color}; font-weight:600; text-transform:uppercase; font-size:0.72rem;">${sc.label}</span>
              </div>
              <div style="background:rgba(255,255,255,0.06); border-radius:4px; overflow:hidden; height:4px;">
                <div style="height:100%; width:${Math.min(100, (s.water_level/s.danger_level*100)).toFixed(0)}%; background:${sc.color}; border-radius:4px;"></div>
              </div>
            </div>
          `, { className: '' });

          marker.on('click', () => onSelect(s.id));
        });
      }

      if (activeLayers.includes('reservoirs')) {
        reservoirs.forEach(r => {
          if (r.lat === undefined || r.lon === undefined || isNaN(r.lat) || isNaN(r.lon)) {
            console.warn(`Reservoir ${r.name || r.id} has missing or invalid coordinates: lat=${r.lat}, lon=${r.lon}`);
            return;
          }
          const pct = r.storage_pct;
          const color = pct > 90 ? '#fb7185' : pct > 75 ? '#fb923c' : '#22d3ee';
          const icon = L.divIcon({
            className: '',
            html: `<div style="
              width:32px; height:32px; border-radius:6px;
              background:${color}20; border:2px solid ${color};
              box-shadow:0 0 16px ${color}50;
              display:flex; align-items:center; justify-content:center;
              color:${color}; font-size:9px; font-weight:700; font-family:monospace;
            ">${pct.toFixed(0)}%</div>`,
            iconSize: [32, 32],
            iconAnchor: [16, 16],
          });
          L.marker([r.lat, r.lon], { icon }).addTo(map)
            .bindPopup(`<div style="font-family:Inter,sans-serif; min-width:180px;">
              <strong style="color:#e2e8f0; font-size:0.88rem;">${r.name}</strong><br/>
              <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:0.75rem;">
                <span style="color:rgba(255,255,255,0.5)">Storage pct:</span>
                <span style="color:${color}; font-weight:600;">${pct.toFixed(1)}%</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-top:2px;">
                <span style="color:rgba(255,255,255,0.5)">Volume:</span>
                <span style="color:${color}; font-weight:600;">${r.current_storage_mcft.toFixed(0)} MCFT</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-top:2px;">
                <span style="color:rgba(255,255,255,0.5)">Spillway flow:</span>
                <span style="color:#fb7185; font-weight:600;">${r.release_cumecs.toFixed(1)} m³/s</span>
              </div>
            </div>`);
        });
      }
    });
  }, [stations, reservoirs, activeLayers]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 520 }} />;
}
