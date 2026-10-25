import { describe,expect,it } from 'vitest'
import { defaultState,decodeState,encodeState,newGroup,parsePatterns,uiPattern } from '../../apps/web/app/utils/state'
describe('URL schema and search notation',()=>{
  it('roundtrips all view fields',()=>{
    const state=defaultState();state.filter.dataset='bkg-2024';state.filter.groups=[newGroup(0),newGroup(1)]
    state.filter.groups[0]!.exclusions=[{mode:'suffix',value:'bach'}]
    state.filter.regions=['state:01'];state.filter.kinds=['district'];state.view='statistics';state.zoom=7.2
    expect(decodeState(encodeState(state))).toEqual(state)
  })
  it('retains separate ing and ingen',()=>expect(parsePatterns('-ing, -ingen','suffix').map(p=>p.value)).toEqual(['ing','ingen']))
  it('only strips the UI suffix notation',()=>{
    expect(uiPattern('-heim','suffix').value).toBe('heim')
    expect(uiPattern('-heim','contains').value).toBe('-heim')
    expect(uiPattern('%_','contains').value).toBe('%_')
  })
  it('rejects unsupported schemas, bad colors and overlarge groups',()=>{
    expect(()=>decodeState('{"version":9}')).toThrow()
    const s=defaultState();s.filter.groups=[newGroup(0)];s.filter.groups[0]!.color='url(evil)'
    expect(()=>encodeState(s)).toThrow()
    s.filter.groups=Array.from({length:11},(_,i)=>newGroup(i));expect(()=>encodeState(s)).toThrow()
  })
  it('rejects duplicate group IDs, controls, inverted bounds and excess state',()=>{
    const s=defaultState();s.filter.groups=[newGroup(0),newGroup(0)];expect(()=>encodeState(s)).toThrow()
    s.filter.groups=[];s.filter.bbox=[10,55,9,54];expect(()=>encodeState(s)).toThrow()
    expect(()=>decodeState('x'.repeat(15001))).toThrow()
  })
})
