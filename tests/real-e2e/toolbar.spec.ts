import {test,expect,type Page} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {mkdir,writeFile} from 'node:fs/promises'
import {selectOverviewFilter} from '../helpers/overview-controls'

test.use({deviceScaleFactor:1})
const ready=(page:Page)=>expect(page.locator('#overview')).toHaveAttribute('data-loaded','true')
const gridRequests=(page:Page)=>{
  const calls:string[]=[]
  page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/v1/grid/'))calls.push(r.url())})
  return calls
}

test('combined toolbar keeps focus, exposes filters and suggestions, and shares the existing state',async({page})=>{
  await page.goto('/');await ready(page)
  const calls=gridRequests(page),input=page.getByLabel('Endung hinzufügen',{exact:true})
  await input.fill(' -bek ');await input.press('Enter');await ready(page)
  await expect(input).toHaveValue('');await expect(input).toBeFocused()
  await expect(page.locator('.toolbar-card-count')).toHaveText('11 Karten')
  expect(calls).toHaveLength(1)
  await input.fill('-burg');await page.getByRole('button',{name:'Hinzufügen',exact:true}).click();await ready(page)
  await expect(input).toBeFocused();await expect(page.locator('.toolbar-card-count')).toHaveText('12 Karten')
  expect(calls).toHaveLength(2)
  await input.fill('BEK');await input.press('Enter')
  await expect(page.locator('[data-ending=bek]')).toHaveClass(/highlighted/)
  await expect(page.locator('[data-ending=bek]')).toBeFocused();expect(calls).toHaveLength(2)
  await page.locator('.overview-toolbar [data-suggestion=büll]').click();await ready(page)
  await expect(input).toBeFocused();await expect(page.locator('.toolbar-card-count')).toHaveText('13 Karten')
  await expect(page.locator('.overview-toolbar [data-suggestion=büll]')).toHaveAttribute('data-active','true')
  await input.fill(' - ');await input.press('Enter');await expect(page.locator('#ending-error')).toContainText('Bitte eine Endung eingeben')
  await input.fill('draftmustnotbeadded')
  const beforeOpen=calls.length
  const mobile=await page.getByRole('button',{name:'Filter',exact:true}).isVisible()
  const trigger=page.getByRole('button',{name:mobile?'Filter':'Weitere Filter',exact:true})
  await trigger.click();await expect(trigger).toHaveAttribute('aria-expanded','true')
  const popup=page.getByRole('dialog',{name:mobile?'Filter':'Weitere Filter',exact:true})
  await expect(popup.getByLabel('Datenbestand',{exact:true})).toBeVisible()
  await popup.getByLabel('Datenbestand',{exact:true}).press('Enter')
  await expect(page.locator('.ending-card')).toHaveCount(13)
  expect(calls).toHaveLength(beforeOpen)
  await page.keyboard.press('Escape')
  if(await popup.isVisible())await page.keyboard.press('Escape')
  await expect(popup).not.toBeVisible();await expect(trigger).toBeFocused()
  expect(calls).toHaveLength(beforeOpen)
  await selectOverviewFilter(page,'Region','state:01');await ready(page)
  await selectOverviewFilter(page,'Ortsart','district');await ready(page)
  const beforeMode=calls.length
  await selectOverviewFilter(page,'Farbmodus','compare')
  await expect(page.locator('.shared-scale .color-range')).toBeVisible()
  await expect.poll(()=>JSON.parse(new URL(page.url()).searchParams.get('s')!).mode).toBe('compare')
  expect(calls).toHaveLength(beforeMode)
  const state=JSON.parse(new URL(page.url()).searchParams.get('s')!)
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(value:string)=>{(window as unknown as {copiedView:string}).copiedView=value}}}))
  await page.getByRole('button',{name:'Ansicht teilen',exact:true}).click()
  await expect(page.locator('.toolbar-notice')).toContainText('Link zur aktuellen Ansicht kopiert')
  const shared=await page.evaluate(()=>(window as unknown as {copiedView:string}).copiedView)
  expect(JSON.parse(new URL(shared).searchParams.get('s')!)).toEqual(state)
  await page.goto(shared);await ready(page)
  expect(JSON.parse(new URL(page.url()).searchParams.get('s')!)).toEqual(state)
  await page.getByRole('button',{name:'Zurücksetzen: Standardendungen wiederherstellen',exact:true}).click();await ready(page)
  const restored=JSON.parse(new URL(page.url()).searchParams.get('s')!)
  expect(restored.endings).toHaveLength(10)
  for(const key of ['region','kind','dataset','mode','grid'])expect(restored[key]).toEqual(state[key])
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('Copy denied')}}}))
  await page.getByRole('button',{name:'Ansicht teilen',exact:true}).click()
  await expect(page.locator('.toolbar-notice[role=alert]')).toContainText('nicht kopiert')
})

test('layout matrix, accessible overlays and resize keep state and requests stable',async({page},info)=>{
  test.skip(info.project.name!=='desktop','One CSS-viewport matrix, alongside the touch-device interaction run.')
  await page.goto('/');await ready(page)
  const calls=gridRequests(page),state=new URL(page.url()).searchParams.get('s'),measurements=[]
  for(const width of [1536,1440,1024,768,390]){
    await page.setViewportSize({width,height:1100})
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
    const toolbar=page.locator('.overview-toolbar')
    const layout=await toolbar.evaluate(node=>({width:node.getBoundingClientRect().width,height:node.getBoundingClientRect().height,top:node.getBoundingClientRect().top}))
    measurements.push({viewport:width,toolbar:layout,firstMapTop:await page.locator('.ending-card').first().evaluate(node=>node.getBoundingClientRect().top)})
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await expect(page.getByLabel('Endung hinzufügen',{exact:true})).toBeVisible()
    expect(new URL(page.url()).searchParams.get('s')).toBe(state)
    expect(calls).toHaveLength(0)
    if(width===1536||width===1440){
      expect(layout.height).toBeGreaterThanOrEqual(130);expect(layout.height).toBeLessThanOrEqual(168)
      await expect(page.locator('.toolbar-visible-filters select')).toHaveCount(3)
      const controls=await page.locator('.toolbar-primary input,.toolbar-primary select,.toolbar-more-filters button').evaluateAll(nodes=>nodes.filter(n=>n.getClientRects().length).map(n=>({top:n.getBoundingClientRect().top,bottom:n.getBoundingClientRect().bottom,height:n.getBoundingClientRect().height})))
      expect(Math.max(...controls.map(c=>c.bottom))-Math.min(...controls.map(c=>c.bottom))).toBeLessThanOrEqual(1)
      for(const control of controls)expect(control.height).toBeGreaterThanOrEqual(44)
      await expect(page.locator('.toolbar-reset')).toHaveText('Zurücksetzen')
      await expect(page.locator('.scale-method')).toHaveText('Methodik')
      await expect(page.locator('.card-order')).toHaveCount(0)
      await expect(page.locator('.card-variants')).toHaveCount(0)
      if(width===1536){
        expect(layout.top).toBeGreaterThanOrEqual(159);expect(layout.top).toBeLessThanOrEqual(167)
        const map=await page.locator('.ending-card').first().boundingBox()
        expect(map!.x).toBeGreaterThanOrEqual(45);expect(map!.x).toBeLessThanOrEqual(49)
        expect(map!.y).toBeGreaterThanOrEqual(370);expect(map!.y).toBeLessThanOrEqual(386)
        expect(map!.width).toBeGreaterThanOrEqual(275);expect(map!.width).toBeLessThanOrEqual(283)
      }
    }
    const mobile=width<768
    const trigger=page.getByRole('button',{name:mobile?'Filter':'Weitere Filter',exact:true})
    await trigger.click()
    const overlay=page.getByRole('dialog',{name:mobile?'Filter':'Weitere Filter',exact:true})
    await expect(overlay).toBeVisible()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.keyboard.press('Escape');await expect(overlay).not.toBeVisible();await expect(trigger).toBeFocused()
    expect(calls).toHaveLength(0)
    await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();scrollTo(0,0)})
    await page.screenshot({path:`artifacts/compact-toolbar-${width===1536?'reference':width===1440?'desktop':width===390?'mobile':width}.png`,fullPage:true,scale:'css'})
  }
  // A 720 CSS-pixel viewport at DPR 2 checks the reflow geometry of 200% zoom
  // on a 1440-pixel display. It is explicitly not a browser-chrome zoom test.
  const cdp=await page.context().newCDPSession(page)
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:720,height:550,deviceScaleFactor:2,mobile:false,screenWidth:1440,screenHeight:1100})
  await expect(page.getByRole('button',{name:'Filter',exact:true})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  expect(new URL(page.url()).searchParams.get('s')).toBe(state);expect(calls).toHaveLength(0)
  await page.screenshot({path:'artifacts/compact-toolbar-200percent-reflow.png',fullPage:true,scale:'css'})
  await mkdir('artifacts',{recursive:true})
  await writeFile('artifacts/compact-toolbar-measurements.json',JSON.stringify({measurements,resizeGridRequests:calls.length,zoomCheck:'720 CSS px at DPR 2; browser-chrome 200% zoom still needs a separate manual check'},null,2))
})
