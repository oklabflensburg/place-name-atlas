import {describe,it,expect,vi} from 'vitest'
import {createOverviewLoader,validateCounts,groupKey,type CommonData} from '../../apps/web/app/utils/overviewLoader'
import {cleanEnding,normalizeEnding,defaultOverview,encodeOverview,decodeOverview,overviewFilter,gridId} from '../../apps/web/app/utils/overview'
import type {GridCounts} from '@atlas/api-client'

const geometry={representation:'circle-centers-v1',dataset:'d',grid:gridId,crs:'EPSG:3035',cell_size:20000,origin:[0,0],viewbox:[3980000,-3040000,80000,80000],bounds:[8,50,9,51],outline:'',cells:[{id:'200_150',cx:4010000,cy:-3010000}]}
const base={dataset:'d',grid:gridId,base_key:'same-base',missing_cells:'no-places',denominator:40,cells:[{id:'200_150',denominator:40}]}
const f=()=>({...overviewFilter(defaultOverview()),dataset:'d'})
function transport(){
  let active=0,maximum=0,fail=false
  const calls:{path:string;filter:ReturnType<typeof f>}[]=[]
  const fetcher=vi.fn(async(path:string,params:{q:string})=>{
    const selected=JSON.parse(params.q);calls.push({path,filter:selected})
    if(path.endsWith('geometry'))return geometry
    if(path.endsWith('base'))return base
    active++;maximum=Math.max(maximum,active)
    await Promise.resolve();active--
    if(fail)throw new Error('Ausfall')
    return {dataset:'d',grid:gridId,base_key:'same-base',missing_counts:'zero',groups:selected.groups.map((g:{id:string})=>({group:g.id,total:10,cells:[{id:'200_150',count:10}]}))}
  })
  return {fetcher:fetcher as never,calls,get maximum(){return maximum},fail:()=>fail=true,recover:()=>fail=false}
}
describe('free endings and immutable comparison data',()=>{
  it('cleans notation and uses NFC + full Unicode casefold, including ß, sigma and Cherokee',()=>{
    expect(cleanEnding('  -be\u0308k  ')).toBe('bëk')
    expect(normalizeEnding('STRAẞE')).toBe(normalizeEnding('strasse'))
    expect(normalizeEnding('ς')).toBe(normalizeEnding('Σ'))
    expect(normalizeEnding('Ꭰ')).toBe(normalizeEnding('ꭰ'))
    for(const raw of ['','  ',' - ','a\u0000'])expect(()=>cleanEnding(raw)).toThrow()
  })
  it('shares twenty ordered cards, variants and an empty selection without a ten-card ceiling',()=>{
    const s=defaultOverview();s.endings.push(...Array.from({length:10},(_,i)=>`neu${i}`));s.variants.push(...Array.from({length:10},()=>[]))
    expect(decodeOverview(encodeOverview(s))).toEqual(s)
    s.endings.reverse();s.variants.reverse();expect(decodeOverview(encodeOverview(s)).endings).toEqual(s.endings)
    s.endings=[];s.variants=[];expect(decodeOverview(encodeOverview(s)).endings).toEqual([])
  })
  it('loads common data once, caches per ending, and requests only the added ending',async()=>{
    const t=transport(),loader=createOverviewLoader(t.fetcher),filter=f(),signal=new AbortController().signal,results=new Map()
    const common=await loader.common(filter,signal)
    await loader.groups(filter,common,signal,(k,v)=>results.set(k,v))
    expect(t.calls.map(c=>c.path)).toEqual(['/api/v1/grid/geometry','/api/v1/grid/base','/api/v1/grid/counts'])
    const old=results.get(groupKey(filter.groups[0]!))
    filter.groups=[{...filter.groups[0]!,id:'new',patterns:[{mode:'suffix',value:'bek'}]}]
    await loader.groups(filter,common,signal,(k,v)=>results.set(k,v))
    expect(t.calls.at(-1)!.filter.groups).toHaveLength(1)
    expect(results.get(groupKey(f().groups[0]!))).toBe(old)
    await loader.groups({...f(),groups:[...f().groups].reverse()},common,signal,()=>{})
    await loader.common(f(),signal)
    expect(t.calls).toHaveLength(4)
  })
  it('batches twenty-five cards and deduplicates simultaneous identical requests',async()=>{
    const t=transport(),loader=createOverviewLoader(t.fetcher),filter=f(),signal=new AbortController().signal
    filter.groups=Array.from({length:25},(_,i)=>({...filter.groups[0]!,id:`g${i}`,patterns:[{mode:'suffix',value:`ending${i}`}]}))
    const shared=await loader.common(filter,signal)
    await Promise.all([loader.groups(filter,shared,signal,()=>{}),loader.groups(filter,shared,signal,()=>{})])
    const calls=t.calls.filter(c=>c.path.endsWith('counts'))
    expect(calls.map(c=>c.filter.groups.length)).toEqual([10,10,5]);expect(t.maximum).toBeLessThanOrEqual(2)
  })
  it('can load suffix counts while geometry is still pending and limits independent additions globally',async()=>{
    const t=transport(),signal=new AbortController().signal
    let release:()=>void=()=>{};const held=new Promise<void>(resolve=>release=resolve)
    const fetcher=async(path:string,params:unknown,init:unknown)=>{if(path.endsWith('geometry'))await held;return (t.fetcher as Function)(path,params,init)}
    const loader=createOverviewLoader(fetcher as never),filter=f()
    const all=loader.common(filter,signal),core=await loader.base(filter,signal)
    await Promise.all(Array.from({length:12},(_,i)=>loader.groups({...filter,groups:[{...filter.groups[0]!,patterns:[{mode:'suffix',value:`new${i}`}]}]},core,signal,()=>{})))
    expect(t.calls.filter(c=>c.path.endsWith('base'))).toHaveLength(1)
    expect(t.calls.filter(c=>c.path.endsWith('counts'))).toHaveLength(12)
    expect(t.maximum).toBeLessThanOrEqual(2)
    release();await all
  })
  it('does not cache failures and ignores superseded results',async()=>{
    const t=transport(),loader=createOverviewLoader(t.fetcher),filter=f(),controller=new AbortController(),received=vi.fn()
    const shared=await loader.common(filter,controller.signal)
    t.fail();await loader.groups(filter,shared,controller.signal,received)
    expect(received.mock.calls.every(c=>c[1]===null&&c[2] instanceof Error)).toBe(true)
    t.recover();received.mockClear();await loader.groups(filter,shared,controller.signal,received)
    expect(received.mock.calls.every(c=>c[1]?.total===10)).toBe(true)
    filter.groups=[{...filter.groups[0]!,patterns:[{mode:'suffix',value:'other'}]}]
    received.mockClear();const pending=loader.groups(filter,shared,controller.signal,received);controller.abort();loader.abandon();await pending
    expect(received).not.toHaveBeenCalled()
  })
  it('rejects missing base data, incompatible sparse semantics and contradictory totals',async()=>{
    const t=transport(),loader=createOverviewLoader(t.fetcher),filter=f(),shared=await loader.common(filter,new AbortController().signal)
    const valid:GridCounts={dataset:'d',grid:gridId,base_key:'same-base',missing_counts:'zero',groups:[{group:'g0',total:0,cells:[]}]}
    expect(()=>validateCounts(valid,shared,filter.groups.slice(0,1))).not.toThrow()
    for(const changed of [{...valid,base_key:'outdated'},{...valid,groups:[{group:'g0',total:1,cells:[]}]},{...valid,groups:[{group:'g0',total:1,cells:[{id:'missing',count:1}]}]}])expect(()=>validateCounts(changed,shared,filter.groups.slice(0,1))).toThrow()
  })
})
