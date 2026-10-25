import {it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import {validateGridData} from '../../apps/web/app/utils/gridGeometry'

// Optional cross-language integration: export with check-grid-offline.py --real.
// Data comes from production SQL/PostGIS, never from a hand-made map fixture.
it.skipIf(!process.env.ATLAS_GRID_CHECK_EXPORT)('renders the real published grid contract produced by PostGIS',()=>{
  const input=JSON.parse(readFileSync(process.env.ATLAS_GRID_CHECK_EXPORT!,'utf8'))
  const checked=validateGridData(input.geometry,input.values,{dataset:'bkg-2024-r3',groups:Array.from({length:10},(_,i)=>`g${i}`)})
  expect(checked.geometry.cells).toHaveLength(1062)
  expect(checked.values.cells).toHaveLength(1006)
  expect(checked.values.denominator).toBe(45858)
  expect(checked.values.totals).toEqual([3218,1342,153,1323,2088,3933,2711,1256,916,60])
})
