import {z} from 'zod'
import type {GridGeometry,GridValues} from '@atlas/api-client'
import {gridId} from './overview'

// Version the wire representation independently from the metric grid. Older
// deployments returned cell paths at the same URL with an immutable HTTP cache.
export const gridRepresentation = 'circle-centers-v1' as const
const coordinate=z.number().finite()
const integer=z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER)
const geometrySchema=z.object({
  representation:z.literal(gridRepresentation),dataset:z.string().min(1),grid:z.literal(gridId),
  crs:z.literal('EPSG:3035'),cell_size:z.literal(20000),origin:z.tuple([z.literal(0),z.literal(0)]),
  viewbox:z.tuple([coordinate,coordinate,coordinate.positive(),coordinate.positive()]),
  bounds:z.tuple([coordinate,coordinate,coordinate,coordinate]),outline:z.string(),
  cells:z.array(z.object({id:z.string().regex(/^-?\d+_-?\d+$/),cx:coordinate,cy:coordinate})).min(1)
})
const valuesSchema=z.object({
  dataset:z.string().min(1),grid:z.literal(gridId),groups:z.array(z.string()),
  denominator:integer,totals:z.array(integer),
  cells:z.array(z.object({id:z.string(),denominator:integer.positive(),counts:z.array(integer)}))
})

/** Validate transport data before making any of the ten maps appear loaded.
 * The geometry contains EPSG:3035 meters, with northing already negated for SVG.
 * A metric viewBox uses exactly the same units; the browser scales it to the
 * stage, without measuring a possibly still-zero container during mounting.
 */
export function validateGridData(rawGeometry:unknown,rawValues:unknown,expected:{dataset:string|null;groups:string[]}):{geometry:GridGeometry;values:GridValues}{
  const parsedGeometry=geometrySchema.safeParse(rawGeometry)
  if(!parsedGeometry.success)throw new Error('Die Rastergeometrie fehlt oder hat ein veraltetes Format. Bitte die Anwendung aktualisieren und erneut laden.')
  const parsedValues=valuesSchema.safeParse(rawValues)
  if(!parsedValues.success)throw new Error('Die Häufigkeitswerte des Rasters sind unvollständig oder ungültig.')
  const g=parsedGeometry.data,v=parsedValues.data
  if(g.dataset!==v.dataset||(expected.dataset!==null&&g.dataset!==expected.dataset))throw new Error('Die Rasterantworten verwenden unterschiedliche Datenstände.')
  if(v.groups.length!==expected.groups.length||v.groups.some((id,i)=>id!==expected.groups[i])||v.totals.length!==v.groups.length)throw new Error('Die Rasterwerte passen nicht zu den gewählten Endungen.')
  const [left,top,width,height]=g.viewbox,r=g.cell_size*.41
  const ids=new Set<string>()
  for(const c of g.cells){
    const [x,y]=c.id.split('_').map(Number)
    if(ids.has(c.id)||c.cx!==(x!+.5)*g.cell_size||c.cy!==-(y!+.5)*g.cell_size)throw new Error('Die Rasterzellen enthalten ungültige Mittelpunkte oder Koordinateneinheiten.')
    if(c.cx-r<left||c.cx+r>left+width||c.cy-r<top||c.cy+r>top+height)throw new Error('Die Rasterzellen liegen außerhalb des gemeinsamen Kartenausschnitts.')
    ids.add(c.id)
  }
  const seen=new Set<string>(),totals=Array<number>(v.groups.length).fill(0)
  let denominator=0
  for(const c of v.cells){
    if(!ids.has(c.id))throw new Error('Für erfasste Orte fehlen Rasterzellen. Bitte die veröffentlichte Datenversion und die Orts-Zell-Zuordnung prüfen.')
    if(seen.has(c.id)||c.counts.length!==totals.length||c.counts.some(n=>n>c.denominator))throw new Error('Das Raster enthält widersprüchliche Häufigkeitswerte.')
    seen.add(c.id);denominator+=c.denominator
    c.counts.forEach((n,i)=>{totals[i]!+=n})
  }
  if(denominator!==v.denominator||totals.some((n,i)=>n!==v.totals[i]))throw new Error('Die Zellwerte stimmen nicht mit den Gesamtzahlen überein.')
  return {geometry:g,values:v}
}
