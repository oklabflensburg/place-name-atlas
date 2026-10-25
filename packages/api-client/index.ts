// Generated from openapi.json by scripts/generate-client.py. Do not edit.

export type BaseCell = { "denominator": number; "id": string }

export type CellPlace = { "id": string; "matching_names": Array<string>; "name": string }

export type CellPlaces = { "cell": string; "count": number; "dataset": string; "denominator": number; "group": string; "items": Array<CellPlace>; "limit": number; "offset": number; "share": number | null }

export type DatasetOut = { "active": boolean; "geometry_date": string; "id": string; "label": string; "place_count": number; "population_date": string; "scope": string; "sources": Array<SourceOut>; "synthetic": boolean }

export type ErrorOut = { "code": string; "message": string; "request_id": string }

export type Filter = { "bbox": [number, number, number, number] | null; "dataset": string | null; "groups": Array<Group>; "kinds": Array<"settlement" | "district">; "regions": Array<string>; "schema_version": 1 }

export type GridBase = { "base_key": string; "cells": Array<BaseCell>; "dataset": string; "denominator": number; "grid": string; "missing_cells": "no-places" }

export type GridCell = { "cx": number; "cy": number; "id": string }

export type GridCounts = { "base_key": string; "dataset": string; "grid": string; "groups": Array<GridHit>; "missing_counts": "zero" }

export type GridGeometry = { "bounds": [number, number, number, number]; "cell_size": number; "cells": Array<GridCell>; "crs": string; "dataset": string; "grid": string; "origin": [number, number]; "outline": string; "representation": "circle-centers-v1"; "viewbox": [number, number, number, number] }

export type GridHit = { "cells": Array<HitCell>; "group": string; "total": number }

export type GridValue = { "counts": Array<number>; "denominator": number; "id": string }

export type GridValues = { "cells": Array<GridValue>; "dataset": string; "denominator": number; "grid": string; "groups": Array<string>; "totals": Array<number> }

export type Group = { "color": string; "exclusions": Array<Pattern>; "id": string; "patterns": Array<Pattern>; "title": string }

export type GroupStatistic = { "count": number; "denominator": number; "group": string; "matched_municipalities": number; "missing_population": number; "municipality_population": number | null; "share": number | null }

export type HitCell = { "count": number; "id": string }

export type Match = { "group": string; "mode": "suffix" | "prefix" | "contains" | "exact"; "name": string; "pattern": string }

export type MunicipalityOut = { "name": string; "population": number | null; "population_date": string; "population_quality": string }

export type Pattern = { "mode": "suffix" | "prefix" | "contains" | "exact"; "value": string }

export type PlaceOut = { "alternatives": Array<string>; "assignment": string; "groups": Array<string>; "id": string; "kind": string; "latitude": number; "longitude": number; "matches": Array<Match>; "municipality": MunicipalityOut | null; "name": string; "regions": Array<RegionOut> }

export type PlacePage = { "dataset": string; "items": Array<PlaceOut>; "limit": number; "offset": number; "total": number }

export type PresetOut = { "comparison": "independent"; "description": string; "groups": Array<Group>; "id": string; "title": string }

export type RegionOut = { "id": string; "level": string; "name": string }

export type RegionalGroupStatistic = { "count": number; "denominator": number; "group": string; "share": number | null }

export type RegionalStatistic = { "denominator": number; "groups": Array<RegionalGroupStatistic>; "region": RegionOut; "total": number }

export type SourceOut = { "attribution": string; "data_date": string; "license": string; "product": string; "url": string; "version": string }

export type StatisticsOut = { "dataset": string; "denominator": number; "denominator_description": string; "groups": Array<GroupStatistic>; "overlap": number; "population_description": string; "regions": Array<RegionalStatistic>; "total": number }

export interface Operations {
  "/api/v1/boundaries": { params: { "q"?: string | null }; response: Record<string, unknown> }
  "/api/v1/datasets": { params: {  }; response: Array<DatasetOut> }
  "/api/v1/export": { params: { "format"?: "csv" | "geojson"; "q"?: string | null }; response: Response }
  "/api/v1/filter-schema": { params: {  }; response: Record<string, unknown> }
  "/api/v1/grid/base": { params: { "q"?: string | null }; response: GridBase }
  "/api/v1/grid/cells/{cell}/places": { params: { "cell": string; "group": string; "limit"?: number; "offset"?: number; "q"?: string | null }; response: CellPlaces }
  "/api/v1/grid/counts": { params: { "q"?: string | null }; response: GridCounts }
  "/api/v1/grid/geometry": { params: { "representation"?: "circle-centers-v1"; "q"?: string | null }; response: GridGeometry }
  "/api/v1/grid/values": { params: { "q"?: string | null }; response: GridValues }
  "/api/v1/places": { params: { "limit"?: number; "offset"?: number; "q"?: string | null }; response: PlacePage }
  "/api/v1/places/{id}": { params: { "id": string; "q"?: string | null }; response: PlaceOut }
  "/api/v1/presets": { params: {  }; response: Array<PresetOut> }
  "/api/v1/regions": { params: { "scope"?: "all" | "overview"; "q"?: string | null }; response: Array<RegionOut> }
  "/api/v1/statistics": { params: { "q"?: string | null }; response: StatisticsOut }
  "/api/v1/tiles/{z}/{x}/{y}.mvt": { params: { "z": number; "x": number; "y": number; "q"?: string | null }; response: Response }
  "/health/instance": { params: {  }; response: Record<string, string> }
  "/health/live": { params: {  }; response: Record<string, string> }
  "/health/ready": { params: {  }; response: Record<string, string> }
}


export async function api<P extends keyof Operations>(path: P, params: Operations[P]['params'] = {} as Operations[P]['params'], init: RequestInit = {}): Promise<Operations[P]['response']> {
  let url: string = path
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (url.includes(`{${key}}`)) url = url.replace(`{${key}}`, encodeURIComponent(String(value)))
    else query.set(key, String(value))
  }
  const response = await fetch(`${url}${query.size ? '?' + query.toString() : ''}`, init)
  if (!response.ok) {
    const body: { message?: string } = await response.json().catch(() => ({}))
    throw new Error(body.message || `Anfrage fehlgeschlagen (${response.status})`)
  }
  if (!response.headers.get('content-type')?.includes('application/json')) return response as Operations[P]['response']
  // Read the body before timing JSON parsing, so transfer is not charged to parsing.
  const bytes = await response.arrayBuffer()
  const start = performance.now()
  const result = JSON.parse(new TextDecoder().decode(bytes))
  performance.measure('atlas:json', { start, end: performance.now(), detail: { path, bytes: bytes.byteLength } })
  return result as Operations[P]['response']
}
