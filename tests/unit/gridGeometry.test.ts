import {describe,it,expect} from 'vitest'
import {validateGridData,gridRepresentation} from '../../apps/web/app/utils/gridGeometry'
import {gridId} from '../../apps/web/app/utils/overview'

function fixture(){
  return {
    geometry:{representation:gridRepresentation,dataset:'published',grid:gridId,crs:'EPSG:3035',cell_size:20000,origin:[0,0],
      viewbox:[3980000,-3040000,80000,80000],bounds:[8,50,9,51],outline:'',cells:[{id:'200_150',cx:4010000,cy:-3010000}]},
    values:{dataset:'published',grid:gridId,groups:['g0','g1'],denominator:40,totals:[10,0],cells:[{id:'200_150',denominator:40,counts:[10,0]}]}
  }
}
const selected={dataset:'published',groups:['g0','g1']}
describe('circle geometry transport regression',()=>{
  it('rejects the formerly cached polygon payload even with correct totals',()=>{
    const {geometry,values}=fixture()
    const legacy={...geometry,representation:undefined,cells:[{id:'200_150',path:'M4000000,-3000000h20000v-20000h-20000z'}]}
    expect(()=>validateGridData(legacy,values,selected)).toThrow('veraltetes Format')
    expect(()=>validateGridData({...legacy,representation:gridRepresentation},values,selected)).toThrow('veraltetes Format')
  })
  it('uses the same metric units and the already inverted Y axis in cells and viewBox',()=>{
    const {geometry,values}=fixture()
    expect(validateGridData(geometry,values,selected)).toEqual({geometry,values})
    // Browser resizing does not change coordinates or require a width measurement.
    expect(geometry.cells[0]!.cx).toBeGreaterThan(geometry.viewbox[0]!)
    expect(geometry.cells[0]!.cy).toBeLessThan(geometry.viewbox[1]!+geometry.viewbox[3]!)
    for(const coords of [{cx:200,cy:150},{cx:8.5,cy:50.5},{cx:4010000,cy:3010000}]){
      expect(()=>validateGridData({...geometry,cells:[{id:'200_150',...coords}]},values,selected)).toThrow('Koordinateneinheiten')
    }
  })
  it('rejects absent cells, missing/nonfinite centers, zero viewBoxes and out of bounds circles',()=>{
    const {geometry,values}=fixture()
    for(const broken of [
      {...geometry,cells:[]},
      {...geometry,cells:[{id:'200_150',cx:NaN,cy:-3010000}]},
      {...geometry,cells:[{id:'200_150',cx:4010000,cy:Infinity}]},
      {...geometry,viewbox:[0,0,0,0]},
      {...geometry,viewbox:[0,0,80000,80000]}
    ])expect(()=>validateGridData(broken,values,selected)).toThrow()
    expect(()=>validateGridData(geometry,{...values,cells:[{...values.cells[0],id:'201_150'}]},selected)).toThrow('fehlen Rasterzellen')
  })
  it('requires per-cell denominators and counts, not only plausible totals',()=>{
    const {geometry,values}=fixture()
    for(const broken of [
      {...values,cells:[]},
      {...values,cells:[{id:'200_150',counts:[10,0]}]},
      {...values,cells:[{id:'200_150',denominator:40,counts:[41,0]}]},
      {...values,cells:[{id:'200_150',denominator:40,counts:[10]}]},
      {...values,cells:[values.cells[0],values.cells[0]]},
      {...values,totals:[9,0]},
      {...values,denominator:41}
    ])expect(()=>validateGridData(geometry,broken,selected)).toThrow()
  })
  it('rejects mismatched datasets, groups and grid versions',()=>{
    const {geometry,values}=fixture()
    expect(()=>validateGridData(geometry,{...values,dataset:'old'},selected)).toThrow('Datenstände')
    expect(()=>validateGridData(geometry,values,{...selected,dataset:'old'})).toThrow('Datenstände')
    expect(()=>validateGridData(geometry,{...values,groups:['g1','g0']},selected)).toThrow('Endungen')
    expect(()=>validateGridData({...geometry,grid:'screen-hexbins'},values,selected)).toThrow('Format')
  })
  it('accepts zero matches and genuinely empty selections while retaining geometry',()=>{
    const {geometry,values}=fixture()
    const noMatches={...values,totals:[0,0],cells:[{...values.cells[0]!,counts:[0,0]}]}
    expect(validateGridData(geometry,noMatches,selected).values.denominator).toBe(40)
    const empty={...values,totals:[0,0],denominator:0,cells:[]}
    expect(validateGridData(geometry,empty,selected).geometry.cells).toHaveLength(1)
  })
})
