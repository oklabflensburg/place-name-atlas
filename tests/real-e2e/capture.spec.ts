import {test,expect} from '@playwright/test'
import {inspectMaps,paintedMap} from '../../scripts/map-browser-check.mjs'

// This export uses one output pixel per CSS pixel. Interaction tests retain
// the device profile's original density and touch settings in real.spec.ts.
test.use({deviceScaleFactor:1})

test('export the loaded overview at CSS resolution',async({page},info)=>{
  await page.goto('/')
  await expect(page.locator('#overview')).toHaveAttribute('data-loaded','true')
  const maps=await inspectMaps(page)
  expect(maps).toHaveLength(10)
  for(const map of maps){
    expect(map.circles).toBe(1062)
    expect(map.finite).toBe(map.circles);expect(map.inside).toBe(map.circles)
  }
  // Test the exported page's real paint as well as its SVG structure.
  for(let i=0;i<10;i++)expect((await paintedMap(page,page.locator('.small-map').nth(i))).coloredPixels).toBeGreaterThan(5)
  await page.evaluate(()=>{
    if(document.activeElement instanceof HTMLElement)document.activeElement.blur()
    scrollTo(0,0)
  })
  // Keep the long mobile page below oversized device-pixel screenshot limits.
  await page.screenshot({path:`artifacts/overview-${info.project.name}-real.png`,fullPage:true,scale:'css'})
})
