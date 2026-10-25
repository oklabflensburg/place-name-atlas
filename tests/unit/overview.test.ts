import { describe,it,expect } from 'vitest'
import { defaultOverview,encodeOverview,decodeOverview,overviewFilter,alternativeMatchNames,cellColor,percent,maxima,initialEndings } from '../../apps/web/app/utils/overview'
describe('ten comparable ending maps',()=>{
  it('explains sted matches through alternative names without confusing stedt',()=>{
    const hit=(name:string)=>({group:'g25',name,mode:'suffix' as const,pattern:'sted'})
    expect(alternativeMatchNames({name:'Silberstedt',matches:[hit('Sølvested')]})).toEqual(['Sølvested'])
    expect(alternativeMatchNames({name:'Borgstedt',matches:[hit('Borgsted'),hit('Borgsted')]})).toEqual(['Borgsted'])
    expect(alternativeMatchNames({name:'Borgsted',matches:[hit('Borgsted'),hit('Borgsted')]})).toEqual([])
    expect(alternativeMatchNames({name:'Borgstedt',matches:[]})).toEqual([])
  })
  it('starts with the editorial ten endings in order',()=>{
    const s=defaultOverview(),f=overviewFilter(s)
    expect(s.endings).toEqual(['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by'])
    expect(f.groups).toHaveLength(10)
    expect(new Set(f.groups.map(g=>g.id)).size).toBe(10)
    expect(f.kinds).toEqual([])
    expect(s.mode).toBe('patterns');expect(s.variants).toEqual(Array.from({length:10},()=>[]))
  })
  it('roundtrips the exact dataset, all filters, mode, grid and Unicode endings',()=>{
    const s=defaultOverview();s.dataset='bkg-2024-r3';s.region='state:01';s.kind='district';s.endings[1]='bü\u0308ll'
    expect(decodeOverview(encodeOverview(s))).toEqual(s)
    expect(overviewFilter(s)).toMatchObject({dataset:s.dataset,regions:['state:01'],kinds:['district']})
  })
  it('replaces each card independently, preserving order and original text',()=>{
    const s=defaultOverview();s.endings[4]='büll'
    expect(overviewFilter(s).groups[4]!.patterns).toEqual([{mode:'suffix',value:'büll'}])
    expect(s.endings.filter((v,i)=>v!==initialEndings[i])).toEqual(['büll'])
  })
  it('uses independent maxima for patterns and one maximum for comparisons',()=>{
    const cells=[{id:'a',denominator:40,counts:[10,1]},{id:'b',denominator:100,counts:[20,2]}]
    const local=maxima(cells,2),shared=Math.max(...local)
    expect(local).toEqual([.25,.025]);expect(shared).toBe(.25)
    expect(cellColor(10,40,local[0])).toBe(cellColor(1,40,local[1]))
    expect(cellColor(10,40,shared)).not.toBe(cellColor(1,40,shared))
    expect(cellColor(10,40,shared)).toBe(cellColor(1,4,shared))
    expect(percent(10,40)).toBe('25 %');expect(percent(.25,1)).toBe('25 %')
  })
  it('handles empty maps, no data, tiny fractions and a single extreme place',()=>{
    expect(maxima([],10)).toEqual(Array(10).fill(0))
    expect(maxima([{id:'a',denominator:0,counts:[0]},{id:'b',denominator:1,counts:[1]}],1)).toEqual([1])
    expect(percent(1,1000000)).toBe('0,0001 %');expect(percent(0,40)).toBe('0 %');expect(percent(0,0)).toBe('Keine Daten')
    expect(cellColor(0,40,0)).not.toBe(cellColor(0,0,0))
    expect(cellColor(1,1000000,1)).not.toBe(cellColor(0,40,1))
    expect(cellColor(1,1,1)).toBe('rgb(16, 76, 67)')
    expect(cellColor(1,1,.25)).toBe('rgb(16, 76, 67)')
    expect(cellColor(0,40,0)).not.toContain('NaN')
  })
  it('keeps variants explicit, optional and in share links',()=>{
    const s=defaultOverview();s.variants[1]=['ing'];s.mode='compare'
    expect(decodeOverview(encodeOverview(s))).toEqual(s)
    expect(overviewFilter(s).groups[1]!.patterns.map(p=>p.value)).toEqual(['ingen','ing'])
    expect(overviewFilter(s).groups[0]!.patterns).toHaveLength(1)
    const old={...s,mode:'share',variants:undefined}
    const restored=decodeOverview(JSON.stringify(old))
    expect(restored.mode).toBe('compare');expect(restored.variants.every(v=>v.length===0)).toBe(true)
    s.variants[0]=Array(8).fill('ing');expect(()=>encodeOverview(s)).toThrow()
  })
  it('rejects missing cards, invalid grid/mode, control characters and unknown versions',()=>{
    expect(()=>decodeOverview(JSON.stringify({...defaultOverview(),endings:['ach']}))).toThrow()
    expect(()=>decodeOverview(JSON.stringify({...defaultOverview(),version:1}))).toThrow()
    expect(()=>decodeOverview(JSON.stringify({...defaultOverview(),grid:'degrees'}))).toThrow()
    expect(()=>decodeOverview(JSON.stringify({...defaultOverview(),mode:'auto'}))).toThrow()
    const s=defaultOverview();s.endings[0]='bad\u0000';expect(()=>encodeOverview(s)).toThrow()
  })
})
