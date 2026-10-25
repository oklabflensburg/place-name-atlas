import {z} from 'zod'
import {api,type Filter,type GridGeometry,type GridBase,type GridCounts,type Group} from '@atlas/api-client'
import {gridId,normalizeEnding} from './overview'
import {gridRepresentation,validateGridData} from './gridGeometry'

export type CardResult={total:number;counts:Record<string,number>;maximum:number}
export type BaseData={base:GridBase;denominators:Record<string,number>}
export type CommonData=BaseData&{geometry:GridGeometry}
type Fetcher=typeof api
const integer=z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER)
const baseSchema=z.object({dataset:z.string(),grid:z.literal(gridId),base_key:z.string(),missing_cells:z.literal('no-places'),denominator:integer,
  cells:z.array(z.object({id:z.string(),denominator:integer.positive()}))})
const countsSchema=z.object({dataset:z.string(),grid:z.literal(gridId),base_key:z.string(),missing_counts:z.literal('zero'),
  groups:z.array(z.object({group:z.string(),total:integer,cells:z.array(z.object({id:z.string(),count:integer.positive()}))}))})

// LRU caches live only for this mounted overview. In-flight promises are kept
// separately and removed on both success and failure, so retry stays possible.
export class Lru<T>{
  private entries=new Map<string,T>()
  constructor(private limit:number){}
  get(key:string){const value=this.entries.get(key);if(value!==undefined){this.entries.delete(key);this.entries.set(key,value)}return value}
  set(key:string,value:T){this.entries.delete(key);this.entries.set(key,value);while(this.entries.size>this.limit)this.entries.delete(this.entries.keys().next().value!)}
}
export const commonKey=(f:Filter)=>JSON.stringify([f.dataset,gridId,f.regions,f.kinds,f.bbox,'all-names-distinct-places-v1'])
export const groupKey=(g:Group)=>JSON.stringify([g.patterns,g.exclusions].map(patterns=>[...new Set(patterns.map(p=>JSON.stringify([p.mode,normalizeEnding(p.value)])))].sort()))

export function createOverviewLoader(fetcher:Fetcher=api){
  const geometryCache=new Lru<GridGeometry>(16),baseCache=new Lru<BaseData>(16),commonCache=new Lru<CommonData>(16),hitCache=new Lru<CardResult>(256)
  const pending=new Map<string,Promise<unknown>>()
  let active=0
  const queue:(()=>void)[]=[]
  async function limited<T>(build:()=>Promise<T>):Promise<T>{
    if(active<2)active++;else await new Promise<void>(resolve=>queue.push(resolve))
    try{return await build()}
    finally{if(queue.length)queue.shift()!();else active--}
  }
  function once<T>(key:string,signal:AbortSignal,build:()=>Promise<T>):Promise<T>{
    const known=pending.get(key)
    if(known)return known as Promise<T>
    const result=build().then(value=>{if(signal.aborted)throw new DOMException('Abgebrochen','AbortError');return value}).finally(()=>{if(pending.get(key)===result)pending.delete(key)})
    pending.set(key,result);return result
  }
  // Aborted operations must not be reused when switching quickly A → B → A.
  function abandon(){pending.clear()}
  async function base(f:Filter,signal:AbortSignal):Promise<BaseData>{
    const key=commonKey(f),known=baseCache.get(key)
    if(known)return known
    return once('denominator:'+key,signal,async()=>{
      const raw=await fetcher('/api/v1/grid/base',{q:JSON.stringify({...f,groups:[]})},{signal})
      const base=baseSchema.parse(raw)
      if(base.dataset!==f.dataset)throw new Error('Die Grundgesamtheit verwendet einen anderen Datenstand.')
      const denominators=Object.fromEntries(base.cells.map(c=>[c.id,c.denominator]))
      if(Object.keys(denominators).length!==base.cells.length||base.cells.reduce((n,c)=>n+c.denominator,0)!==base.denominator)throw new Error('Die Grundgesamtheit enthält widersprüchliche Zellzahlen.')
      const result={base,denominators}
      if(!signal.aborted)baseCache.set(key,result)
      return result
    })
  }
  async function common(f:Filter,signal:AbortSignal):Promise<CommonData>{
    const key=commonKey(f),known=commonCache.get(key)
    if(known)return known
    return once('base:'+key,signal,async()=>{
      const geometryKey=JSON.stringify([f.dataset,gridId,f.regions,f.bbox])
      const [geometry,core]=await Promise.all([
        geometryCache.get(geometryKey)??fetcher('/api/v1/grid/geometry',{q:JSON.stringify({...f,groups:[],kinds:[]}),representation:gridRepresentation},{signal,cache:'no-cache'}),
        base(f,signal)])
      const sharedBase=core.base
      const started=performance.now()
      const checked=validateGridData(geometry,{...sharedBase,groups:[],totals:[],cells:sharedBase.cells.map(c=>({...c,counts:[]}))},{dataset:f.dataset,groups:[]})
      const result={geometry:checked.geometry,...core}
      performance.measure('atlas:common-processing',{start:started,end:performance.now()})
      if(!signal.aborted){geometryCache.set(geometryKey,checked.geometry);commonCache.set(key,result)}
      return result
    })
  }
  async function groups(f:Filter,shared:BaseData,signal:AbortSignal,onResult:(key:string,result:CardResult|null,error?:unknown)=>void){
    const baseKey=commonKey(f),missing:Group[]=[],waiting:Promise<unknown>[]=[]
    const reservations=new Map<string,{resolve:(v:CardResult)=>void;reject:(e:unknown)=>void}>()
    for(const g of f.groups){
      const key=groupKey(g),cacheKey=baseKey+key,known=hitCache.get(cacheKey)
      if(known){onResult(key,known);continue}
      let promise=pending.get(cacheKey) as Promise<CardResult>|undefined
      if(!promise){
        promise=new Promise<CardResult>((resolve,reject)=>reservations.set(cacheKey,{resolve,reject}))
        pending.set(cacheKey,promise);missing.push(g)
      }
      const current=promise
      waiting.push(promise.then(result=>{if(!signal.aborted)onResult(key,result)},error=>{if(!signal.aborted)onResult(key,null,error)}).finally(()=>{if(pending.get(cacheKey)===current)pending.delete(cacheKey)}))
    }
    const batches:Group[][]=[]
    for(let i=0;i<missing.length;i+=10)batches.push(missing.slice(i,i+10))
    async function worker(){
      while(batches.length){
        const batch=batches.shift()!
        try{
          if(signal.aborted)throw new DOMException('Abgebrochen','AbortError')
          const data=countsSchema.parse(await limited(()=>{
            if(signal.aborted)throw new DOMException('Abgebrochen','AbortError')
            return fetcher('/api/v1/grid/counts',{q:JSON.stringify({...f,groups:batch})},{signal})
          }))
          const started=performance.now()
          validateCounts(data,shared,batch)
          for(const [i,g] of batch.entries()){
            const hit=data.groups[i]!,key=baseKey+groupKey(g)
            const counts=Object.fromEntries(hit.cells.map(c=>[c.id,c.count]))
            const result={counts,total:hit.total,maximum:Math.max(0,...hit.cells.map(c=>c.count/shared.denominators[c.id]!))}
            if(!signal.aborted)hitCache.set(key,result)
            reservations.get(key)!.resolve(result)
          }
          performance.measure('atlas:counts-processing',{start:started,end:performance.now()})
        }catch(error){for(const g of batch)reservations.get(baseKey+groupKey(g))!.reject(error)}
      }
    }
    await Promise.all([worker(),worker(),...waiting])
  }
  return {base,common,groups,abandon}
}

export function validateCounts(data:GridCounts,shared:BaseData,groups:Group[]){
  if(data.dataset!==shared.base.dataset||data.grid!==shared.base.grid||data.base_key!==shared.base.base_key||data.missing_counts!=='zero')throw new Error('Treffer und Grundgesamtheit verwenden unterschiedliche Daten oder Suchregeln.')
  if(data.groups.length!==groups.length)throw new Error('Die Trefferantwort ist unvollständig.')
  data.groups.forEach((g,i)=>{
    if(g.group!==groups[i]!.id)throw new Error('Die Treffer passen nicht zu den gewählten Endungen.')
    let total=0;const seen=new Set<string>()
    for(const c of g.cells){
      if(seen.has(c.id)||!shared.denominators[c.id]||c.count>shared.denominators[c.id]!)throw new Error('Für Treffer fehlen gültige Grunddaten.')
      seen.add(c.id);total+=c.count
    }
    if(total!==g.total)throw new Error('Zelltreffer und Gesamtzahl widersprechen sich.')
  })
}
