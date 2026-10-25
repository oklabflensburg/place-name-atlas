import { z } from 'zod'
import type { Filter, Group, Pattern } from '@atlas/api-client'

const pattern = z.object({ mode: z.enum(['suffix','prefix','contains','exact']), value: z.string().min(1).max(80).refine(v => !!v.trim() && !/\p{C}/u.test(v)) }).strict()
const group = z.object({ id: z.string().regex(/^[a-zA-Z0-9-]{1,24}$/), title: z.string().min(1).max(60),
  color: z.string().regex(/^#[\da-f]{6}$/i), patterns: z.array(pattern).min(1).max(8), exclusions: z.array(pattern).max(8) }).strict()
const filterSchema = z.object({ schema_version: z.literal(1), dataset: z.string().min(1).max(100).nullable(),
  groups: z.array(group).max(10), regions: z.array(z.string().regex(/^(state|district|municipality):\d{2,12}$/)).max(12),
  kinds: z.array(z.enum(['settlement','district'])).max(2), bbox: z.tuple([z.number(),z.number(),z.number(),z.number()]).nullable() }).strict()
export const stateSchema = z.object({ version: z.literal(1), filter: filterSchema,
  center: z.tuple([z.number().min(-180).max(180),z.number().min(-85).max(85)]), zoom: z.number().min(0).max(14),
  view: z.enum(['map','list','statistics']) }).strict()
  .refine(v => new Set(v.filter.groups.map(g => g.id)).size === v.filter.groups.length)
  .refine(v => !v.filter.bbox || (v.filter.bbox[0]<v.filter.bbox[2] && v.filter.bbox[1]<v.filter.bbox[3]
    && v.filter.bbox[0]>=-180 && v.filter.bbox[2]<=180 && v.filter.bbox[1]>=-85.051129 && v.filter.bbox[3]<=85.051129))

export type ViewState = z.infer<typeof stateSchema>
export const newGroup = (index: number): Group => ({ id: `g${index+1}`, title: `Gruppe ${index+1}`,
  color: ['#126b61','#b95030','#6953a5','#a16c12'][index] || '#126b61', patterns: [{ mode:'suffix', value: 'by' }], exclusions:[] })
export function defaultState(): ViewState {
  return { version:1, filter:{ schema_version:1,dataset:null,groups:[],regions:[],kinds:[],bbox:null },center:[10.25,51.2],zoom:4,view:'map' }
}
export function encodeState(state: ViewState): string {
  const parsed=stateSchema.parse(state)
  return JSON.stringify(parsed)
}
export function decodeState(raw: string): ViewState {
  if (raw.length>15000) throw new Error('Der Ansichtslink ist zu lang.')
  return stateSchema.parse(JSON.parse(raw))
}
export function uiPattern(value: string, mode: Pattern['mode']): Pattern {
  return { mode, value: mode==='suffix' && value.startsWith('-') ? value.slice(1) : value }
}
export function parsePatterns(input: string, mode: Pattern['mode']): Pattern[] {
  return input.split(',').map(v => uiPattern(v.trim(),mode)).filter(v => !!v.value)
}
export function validateFilter(filter: Filter) { return filterSchema.parse(filter) }
