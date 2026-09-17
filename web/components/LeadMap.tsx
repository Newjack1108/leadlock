'use client';

import { useState, useEffect, useCallback } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import type { DashboardPresetPeriod, DateRangeQueryParams, LeadLocationItem } from '@/lib/types';
import { getLeadLocations, getOrderLocations } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Maximize2 } from 'lucide-react';
import 'leaflet/dist/leaflet.css';

type DatePeriod = DashboardPresetPeriod;
type LeadMapPeriod = DatePeriod | 'custom';

const PERIODS: { value: DatePeriod; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
];

function MapMarkers({
  locations,
  kind,
}: {
  locations: LeadLocationItem[];
  kind: 'lead' | 'order';
}) {
  const isLead = kind === 'lead';
  return (
    <>
      {locations.map((loc, i) => (
        <CircleMarker
          key={`${kind}-${loc.postcode}-${i}`}
          center={[loc.lat, loc.lng]}
          radius={6}
          pathOptions={{
            fillColor: isLead ? '#22c55e' : '#3b82f6',
            color: isLead ? '#16a34a' : '#2563eb',
            weight: 1,
            fillOpacity: 1,
            opacity: 1,
          }}
        >
          <Popup>
            <span className="font-medium">{loc.postcode}</span>
            <br />
            <span className="text-muted-foreground">
              {loc.count} {isLead ? 'lead' : 'order'}
              {loc.count !== 1 ? 's' : ''}
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
  period?: LeadMapPeriod;
  /** Used when fetching order locations for the current dashboard filter (incl. custom range). */
  dateRange?: DateRangeQueryParams;
  periodLabel?: string;
  height?: number;
}

export default function LeadMap({
  locations,
  loading = false,
  period = 'all',
  dateRange,
  periodLabel,
  height = 300,
}: LeadMapProps) {
  const [expanded, setExpanded] = useState(false);
  const [modalPeriod, setModalPeriod] = useState<LeadMapPeriod>(period);
  const [modalLocations, setModalLocations] = useState<LeadLocationItem[]>(locations);
  const [modalLoading, setModalLoading] = useState(false);
  const [showLeads, setShowLeads] = useState(true);
  const [showOrders, setShowOrders] = useState(false);
  const [orderLocations, setOrderLocations] = useState<LeadLocationItem[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);

  const orderFilterForPeriod = useCallback(
    (activePeriod: LeadMapPeriod): DateRangeQueryParams => {
      if (activePeriod === 'custom') {
        if (dateRange?.start_date && dateRange?.end_date) {
          return { start_date: dateRange.start_date, end_date: dateRange.end_date };
        }
        return { period: 'all' };
      }
      return { period: activePeriod };
    },
    [dateRange]
  );

  const fetchOrderLocations = useCallback(
    async (activePeriod: LeadMapPeriod) => {
      setOrdersLoading(true);
      try {
        const res = await getOrderLocations(orderFilterForPeriod(activePeriod));
        setOrderLocations(Array.isArray(res) ? res : []);
      } catch {
        setOrderLocations([]);
      } finally {
        setOrdersLoading(false);
      }
    },
    [orderFilterForPeriod]
  );

  // Sync modal period when opening with dashboard period
  useEffect(() => {
    if (expanded) {
      setModalPeriod(period);
      setModalLocations(locations);
    }
  }, [expanded, period, locations]);

  // Fetch order locations when toggle is on or period changes while on
  useEffect(() => {
    if (!showOrders) return;
    const activePeriod = expanded ? modalPeriod : period;
    void fetchOrderLocations(activePeriod);
  }, [showOrders, expanded, modalPeriod, period, fetchOrderLocations]);

  const handlePeriodChange = async (newPeriod: DatePeriod) => {
    setModalPeriod(newPeriod);
    setModalLoading(true);
    try {
      const res = await getLeadLocations({ period: newPeriod });
      setModalLocations(Array.isArray(res) ? res : []);
    } catch {
      setModalLocations([]);
    } finally {
      setModalLoading(false);
    }
  };

  const handleToggleLeads = () => {
    setShowLeads((prev) => !prev);
  };

  const handleToggleOrders = () => {
    setShowOrders((prev) => !prev);
  };

  const hasLeadData = locations && locations.length > 0;
  const hasLeadMarkers = showLeads && hasLeadData;
  const hasOrderMarkers = showOrders && orderLocations.length > 0;
  const showEmpty =
    !loading &&
    !hasLeadData &&
    !(showOrders && (ordersLoading || hasOrderMarkers));

  const layerToggles = (
    <div className="absolute top-2 left-2 z-[1000] flex flex-wrap gap-1.5">
      <Button
        variant={showLeads ? 'default' : 'secondary'}
        size="sm"
        className="shadow-md"
        onClick={handleToggleLeads}
        type="button"
      >
        {showLeads ? 'Hide leads' : 'Show leads'}
      </Button>
      <Button
        variant={showOrders ? 'default' : 'secondary'}
        size="sm"
        className="shadow-md"
        onClick={handleToggleOrders}
        type="button"
        disabled={ordersLoading}
      >
        {ordersLoading ? 'Loading…' : showOrders ? 'Hide orders' : 'Show orders'}
      </Button>
    </div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-border bg-muted/30" style={{ height }}>
        <p className="text-sm text-muted-foreground">Loading map...</p>
      </div>
    );
  }

  if (showEmpty) {
    return (
      <div className="relative flex flex-col items-center justify-center gap-1 rounded-lg border border-border bg-muted/30 px-4 text-center" style={{ height }}>
        <p className="text-sm text-muted-foreground">
          No leads with postcodes in this period
        </p>
        <p className="text-xs text-muted-foreground">
          Add postcodes to leads or customers to see them on the map. Try &quot;All&quot; for all-time.
        </p>
        {layerToggles}
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
          {hasLeadMarkers && <MapMarkers locations={locations} kind="lead" />}
          {hasOrderMarkers && <MapMarkers locations={orderLocations} kind="order" />}
        </MapContainer>
        {layerToggles}
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
            <div className="flex flex-wrap items-center gap-2 pt-2">
              {modalPeriod === 'custom' && (
                <Button variant="default" size="sm" disabled type="button">
                  Custom
                </Button>
              )}
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
              <Button
                variant={showLeads ? 'default' : 'outline'}
                size="sm"
                onClick={handleToggleLeads}
                type="button"
              >
                {showLeads ? 'Hide leads' : 'Show leads'}
              </Button>
              <Button
                variant={showOrders ? 'default' : 'outline'}
                size="sm"
                onClick={handleToggleOrders}
                disabled={ordersLoading}
                type="button"
              >
                {ordersLoading ? 'Loading…' : showOrders ? 'Hide orders' : 'Show orders'}
              </Button>
            </div>
            {modalPeriod === 'custom' && periodLabel && (
              <p className="pt-2 text-sm text-muted-foreground">Showing: {periodLabel}</p>
            )}
            {(showLeads || showOrders) && (
              <p className="pt-1 text-xs text-muted-foreground">
                Green = leads · Blue = accepted orders
              </p>
            )}
          </DialogHeader>
          <div className="flex-1 min-h-0 px-6 pb-6">
            {modalLoading ? (
              <div className="flex h-full min-h-[400px] items-center justify-center rounded-lg border border-border bg-muted/30">
                <p className="text-sm text-muted-foreground">Loading map...</p>
              </div>
            ) : !(showLeads && modalLocations && modalLocations.length > 0) &&
              !(showOrders && orderLocations.length > 0) ? (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center gap-1 rounded-lg border border-border bg-muted/30 px-4 text-center">
                <p className="text-sm text-muted-foreground">
                  {!showLeads && !showOrders
                    ? 'Turn on leads or orders to see locations'
                    : 'No locations with postcodes in this period'}
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
                  {showLeads && modalLocations && modalLocations.length > 0 && (
                    <MapMarkers locations={modalLocations} kind="lead" />
                  )}
                  {showOrders && orderLocations.length > 0 && (
                    <MapMarkers locations={orderLocations} kind="order" />
                  )}
                </MapContainer>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
