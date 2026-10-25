import { z } from 'zod'
import type { Filter, Group, GridValue, PlaceOut } from '@atlas/api-client'
import casefold from './casefold.json'
import {interpolateRgb} from 'd3-interpolate'
import {formatLocale} from 'd3-format'

export const initialEndings = ['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by']
export const suggestions = [...initialEndings,'ing','burg','berg','bek','büttel','büll','leben','rode']
export const gridId = 'laea-3035-square-20000-origin-0-v1'
const suffix = z.string().min(1).refine(v=>Array.from(v).length<=80&&!!v.trim()&&!/\p{C}/u.test(v))
export const overviewSchema = z.object({
  version:z.literal(2), endings:z.array(suffix),
  region:z.string().regex(/^(state|district|municipality):\d{2,12}$/).or(z.literal('')),
  kind:z.enum(['','settlement','district']),dataset:z.string().min(1).max(100).nullable(),
  variants:z.array(z.array(suffix).max(7)),
  mode:z.enum(['patterns','compare']),grid:z.literal(gridId)
}).strict().refine(s=>s.endings.length===s.variants.length,'Endungen und Varianten passen nicht zusammen.')
export type OverviewState = z.infer<typeof overviewSchema>
export const defaultOverview = ():OverviewState=>({version:2,endings:[...initialEndings],variants:Array.from({length:10},()=>[]),region:'',kind:'',dataset:null,mode:'patterns',grid:gridId})
export const encodeOverview = (s:OverviewState)=>{
  const raw=JSON.stringify(overviewSchema.parse(s))
  if(encodeURIComponent(raw).length>48000)throw new Error('Die Ansicht ist zu groß für einen teilbaren Link (48.000 URL-Zeichen). Bitte Endungen oder Varianten kürzen.')
  return raw
}
export function decodeOverview(raw:string):OverviewState {
  if(encodeURIComponent(raw).length>48000)throw new Error('Der Ansichtslink überschreitet 48.000 URL-Zeichen.')
  try{const value=JSON.parse(raw);if(value.mode==='share')value.mode='compare';value.variants??=value.endings.map(()=>[]);return overviewSchema.parse(value)}
  catch{throw new Error('Dieser Ansichtslink ist ungültig oder nutzt ein veraltetes URL-Schema. Über Zurücksetzen kannst du die Übersicht neu öffnen.')}
}
export function overviewFilter(s:OverviewState):Filter {
  return {schema_version:1,dataset:s.dataset,regions:s.region?[s.region]:[],kinds:s.kind?[s.kind]:[],bbox:null,
    groups:s.endings.map((value,i):Group=>({id:`g${i}`,title:Array.from(`-${value}`).slice(0,60).join(''),color:'#126b61',patterns:[value,...s.variants[i]!].map(value=>({mode:'suffix',value})),exclusions:[]}))}
}
export function alternativeMatchNames(place:Pick<PlaceOut,'name'|'matches'>):string[] {
  const names=[...new Set(place.matches.map(match=>match.name))]
  return names.includes(place.name)?[]:names
}
// All occupied cells enter the maximum, including cells with only one place.
// Fractions stay in [0,1]; only percent() converts them to percentages.
export function maxima(cells:GridValue[],cards=cells[0]?.counts.length??0):number[] {
  const result=Array<number>(cards).fill(0)
  for(const c of cells)if(c.denominator>0)for(let i=0;i<cards;i++)result[i]=Math.max(result[i]!, (c.counts[i]||0)/c.denominator)
  return result
}
export const normalizeEnding=(value:string)=>Array.from(value.normalize('NFC'),c=>(casefold as Record<string,string>)[c]??c.toLowerCase()).join('').normalize('NFC')
export function cleanEnding(raw:string):string {
  const value=raw.trim().replace(/^-/,'').trim().normalize('NFC')
  if(!value)throw new Error('Bitte eine Endung eingeben, zum Beispiel -bek.')
  if(Array.from(value).length>80||/\p{C}/u.test(value))throw new Error('Eine Endung darf höchstens 80 Zeichen und keine Steuerzeichen enthalten.')
  return value
}
export const endingKey=(value:string,variants:string[]=[])=>JSON.stringify([...new Set([value,...variants].map(normalizeEnding))].sort())
export const zeroColor='#edf0e7',noDataColor='#dedfd8'
const ramp=[interpolateRgb('rgb(181,212,181)','rgb(77,148,126)'),interpolateRgb('rgb(77,148,126)','rgb(16,76,67)')]
export const scaleGradient='linear-gradient(to right, rgb(181,212,181), rgb(77,148,126), rgb(16,76,67))'
export function cellColor(count:number,denominator:number,maximum=1):string {
  if(denominator<=0)return noDataColor
  if(count<=0)return zeroColor
  const t=Math.min(1,Math.max(0,maximum>0?count/denominator/maximum:1))*2
  const index=Math.min(1,Math.floor(t)),fraction=t-index
  return ramp[index]!(fraction)
}
const locale=formatLocale({decimal:',',thousands:'.',grouping:[3],currency:['',' €'],percent:' %'})
export const number = locale.format(',.0f')
const formatPercent=locale.format('.2~%'),smallPercent=locale.format('.2~g')
export function percent(n:number,d:number):string {
  if(!d)return 'Keine Daten'
  const value=n/d*100
  return value>0&&value<.01?`${smallPercent(value)} %`:formatPercent(n/d)
}
