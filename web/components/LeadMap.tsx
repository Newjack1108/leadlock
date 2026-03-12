'use client';

import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import type { LeadLocationItem } from '@/lib/types';
import { getLeadLocations } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Maximize2 } from 'lucide-react';
import 'leaflet/dist/leaflet.css';

type DatePeriod = 'all' | 'week' | 'month' | 'quarter' | 'year';

const PERIODS: { value: DatePeriod; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
];

function MapMarkers({ locations }: { locations: LeadLocationItem[] }) {
  return (
    <>
      {locations.map((loc, i) => (
        <CircleMarker
          key={`${loc.postcode}-${i}`}
          center={[loc.lat, loc.lng]}
          radius={6}
          pathOptions={{
            fillColor: '#22c55e',
            color: '#16a34a',
            weight: 1,
            fillOpacity: 1,
            opacity: 1,
          }}
        >
          <Popup>
            <span className="font-medium">{loc.postcode}</span>
            <br />
            <span className="text-muted-foreground">
              {loc.count} lead{loc.count !== 1 ? 's' : ''}
            </span>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}

interface LeadMapProps {
  locations: LeadLocationItem[];
  loading?: boolean;
  period?: DatePeriod;
  height?: number;
}

export default function LeadMap({ locations, loading = false, period = 'all', height = 300 }: LeadMapProps) {
  const [expanded, setExpanded] = useState(false);
  const [modalPeriod, setModalPeriod] = useState<DatePeriod>(period);
  const [modalLocations, setModalLocations] = useState<LeadLocationItem[]>(locations);
  const [modalLoading, setModalLoading] = useState(false);

  // Sync modal period when opening with dashboard period
  useEffect(() => {
    if (expanded) {
      setModalPeriod(period);
      setModalLocations(locations);
    }
  }, [expanded, period, locations]);

  const handlePeriodChange = async (newPeriod: DatePeriod) => {
    setModalPeriod(newPeriod);
    setModalLoading(true);
    try {
      const res = await getLeadLocations(newPeriod === 'all' ? undefined : newPeriod);
      setModalLocations(Array.isArray(res) ? res : []);
    } catch {
      setModalLocations([]);
    } finally {
      setModalLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-border bg-muted/30" style={{ height }}>
        <p className="text-sm text-muted-foreground">Loading map...</p>
      </div>
    );
  }

  if (!locations || locations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-border bg-muted/30 px-4 text-center" style={{ height }}>
        <p className="text-sm text-muted-foreground">
          No leads with postcodes in this period
        </p>
        <p className="text-xs text-muted-foreground">
          Add postcodes to leads or customers to see them on the map. Try &quot;All&quot; for all-time.
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        className={`relative w-full overflow-hidden rounded-lg transition-opacity duration-200 ${
          expanded ? 'opacity-50 pointer-events-none' : ''
        }`}
        style={{ height }}
      >
        <MapContainer
          center={[54.5, -2.5]}
          zoom={6}
          scrollWheelZoom={false}
          className="h-full w-full"
          attributionControl={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapMarkers locations={locations} />
        </MapContainer>
        <Button
          variant="secondary"
          size="sm"
          className="absolute top-2 right-2 z-[1000] gap-1.5 shadow-md"
          onClick={() => setExpanded(true)}
          type="button"
        >
          <Maximize2 className="h-4 w-4" />
          Expand
        </Button>
      </div>

      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="max-w-6xl w-[90vw] h-[85vh] flex flex-col gap-4 p-0">
          <DialogHeader className="px-6 pt-6 pb-0">
            <DialogTitle>Lead Locations</DialogTitle>
            <div className="flex flex-wrap gap-2 pt-2">
              {PERIODS.map((p) => (
                <Button
                  key={p.value}
                  variant={modalPeriod === p.value ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handlePeriodChange(p.value)}
                  disabled={modalLoading}
                  type="button"
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </DialogHeader>
          <div className="flex-1 min-h-0 px-6 pb-6">
            {modalLoading ? (
              <div className="flex h-full min-h-[400px] items-center justify-center rounded-lg border border-border bg-muted/30">
                <p className="text-sm text-muted-foreground">Loading map...</p>
              </div>
            ) : !modalLocations || modalLocations.length === 0 ? (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center gap-1 rounded-lg border border-border bg-muted/30 px-4 text-center">
                <p className="text-sm text-muted-foreground">
                  No leads with postcodes in this period
                </p>
              </div>
            ) : (
              <div className="h-full min-h-[400px] rounded-lg overflow-hidden">
                <MapContainer
                  center={[54.5, -2.5]}
                  zoom={5}
                  scrollWheelZoom
                  className="h-full w-full"
                  attributionControl={false}
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <MapMarkers locations={modalLocations} />
                </MapContainer>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
