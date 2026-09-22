'use client';

import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';

import type { ExcludedPartner, PartnerCard } from '@sm/contracts/client';
import L from 'leaflet';
import 'leaflet.markercluster';
import { useEffect, useRef } from 'react';

// Colour per partner type; the legend lives in the list view so the map stays uncluttered.
const TYPE_COLOR: Record<string, string> = { SCA: '#0B3D91', PSB: '#1B7F4B', RRB: '#E07A1F', NBFC_MFI: '#6B46C1' };

function pin(color: string, dimmed: boolean) {
  return L.divIcon({
    className: '',
    iconSize: [28, 36],
    iconAnchor: [14, 34],
    html: `<svg width="28" height="36" viewBox="0 0 28 36" aria-hidden="true" style="opacity:${dimmed ? 0.45 : 1}"><path d="M14 35s12-11 12-21A12 12 0 0 0 2 14c0 10 12 21 12 21Z" fill="${dimmed ? '#7A8699' : color}" stroke="#fff" stroke-width="2"/><circle cx="14" cy="14" r="4.5" fill="#fff"/></svg>`,
  });
}

/** Loaded only when the citizen opens the map (dynamic import), never on the list view. */
export default function PartnerMap({
  center,
  partners,
  excluded,
  selectedId,
  onSelect,
  onTilesFailed,
}: {
  center: { lat: number; lng: number };
  partners: PartnerCard[];
  excluded: ExcludedPartner[];
  selectedId: string | null;
  onSelect: (p: PartnerCard) => void;
  onTilesFailed: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const map = L.map(ref.current, { zoomControl: true, attributionControl: true }).setView([center.lat, center.lng], 11);
    mapRef.current = map;
    let tileErrors = 0;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '© OpenStreetMap contributors',
    })
      .on('tileerror', () => {
        tileErrors += 1;
        if (tileErrors === 4) onTilesFailed(); // spec §13: map tiles down → list view
      })
      .addTo(map);
    L.circleMarker([center.lat, center.lng], { radius: 7, color: '#fff', weight: 3, fillColor: '#E07A1F', fillOpacity: 1 }).addTo(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // The map is created once per mount; markers update below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 40 });
    for (const p of partners) {
      const marker = L.marker([p.lat, p.lng], { icon: pin(TYPE_COLOR[p.type] ?? '#0B3D91', false), title: p.name, keyboard: true });
      marker.on('click', () => onSelect(p));
      if (p.id === selectedId) marker.setZIndexOffset(1000);
      cluster.addLayer(marker);
    }
    for (const p of excluded) {
      cluster.addLayer(L.marker([p.lat, p.lng], { icon: pin('#7A8699', true), title: p.name, keyboard: false }));
    }
    map.addLayer(cluster);
    const bounds = L.latLngBounds([[center.lat, center.lng], ...partners.map((p) => [p.lat, p.lng] as [number, number])]);
    if (partners.length) map.fitBounds(bounds.pad(0.2), { maxZoom: 13 });
    return () => {
      map.removeLayer(cluster);
    };
  }, [partners, excluded, selectedId, onSelect, center.lat, center.lng]);

  return <div ref={ref} className="h-80 w-full overflow-hidden rounded-xl border border-border" role="application" aria-label="Map" />;
}
