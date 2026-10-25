import {selectOverviewFilter} from '../helpers/overview-controls'
import {test,expect,type Page} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {identities,matches} from '../../scripts/local-runtime.mjs'
import {inspectMaps,paintedMap} from '../../scripts/map-browser-check.mjs'
const totals=['3.218','1.342','153','1.323','2.088','3.933','2.711','1.256','916','60']
async function ready(page:Page){await expect(page.locator('#overview')).toHaveAttribute('data-loaded','true')}
async function visibleMaps(page:Page){
  const maps=await inspectMaps(page)
  expect(maps).toHaveLength(10)
  for(const map of maps){
    expect(map.svg).toBe(true)
    expect(map.size?.width).toBeGreaterThan(40);expect(map.size?.height).toBeGreaterThan(40)
    expect(map.circles).toBeGreaterThan(0)
    expect(map.finite).toBe(map.circles);expect(map.inside).toBe(map.circles);expect(map.visible).toBe(map.circles)
  }
  for(const [i,map] of maps.entries()){
    const paint=await paintedMap(page,page.locator('svg.small-map').nth(i))
    expect(paint.circlePixels,`painted circles for -${map.ending}`).toBeGreaterThan(10)
    if(map.matching>0)expect(paint.coloredPixels,`painted matching circles for -${map.ending}`).toBeGreaterThan(5)
  }
}

test('legacy polygon response cannot masquerade as successfully loaded circle maps',async({page})=>{
  // Fault injection reproduces the old cached wire format. All other requests
  // and the recovery use the actual published data through nginx.
  await page.route('**/api/v1/grid/geometry?**',async route=>{
    expect(new URL(route.request().url()).searchParams.get('representation')).toBe('circle-centers-v1')
    const response=await route.fetch(),legacy=await response.json()
    delete legacy.representation
    legacy.cells=legacy.cells.map((c:{id:string})=>({id:c.id,path:'M0,0h20000v20000z'}))
    await route.fulfill({response,json:legacy})
  })
  await page.goto('/')
  await expect(page.locator('.error-panel')).toContainText('veraltetes Format')
  await expect(page.locator('#overview')).toHaveAttribute('data-loaded','false')
  await expect(page.locator('.ending-card')).toHaveCount(10)
  await expect(page.locator('.small-map')).toHaveCount(0)
  await expect(page.locator('.card-count strong')).toHaveCount(0)
  await expect(page.locator('.map-state')).toHaveText(Array(10).fill('Kartendaten nicht verfügbar'))
  await page.unroute('**/api/v1/grid/geometry?**')
  await page.getByRole('button',{name:'Erneut versuchen',exact:true}).click()
  await ready(page);await visibleMaps(page)
})

test('real GN250 circles, color modes, hover/touch, variants, regions and screenshots through nginx',async({page,request},info)=>{
  // Reusing a listener is allowed only after validating the actual upstreams.
  const expected=identities('preview')
  for(const [path,identity] of [['/health/proxy',expected.nginx],['/health/instance',expected.api],['/health/web',expected.web]] as const){
    const response=await request.get(path);expect(response.ok()).toBe(true)
    expect(matches(await response.json(),identity)).toBe(true)
  }
  const failures:string[]=[]
  page.on('pageerror',e=>failures.push(e.message))
  page.on('console',m=>{if(m.type()==='error')failures.push(m.text())})
  page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)failures.push(`${r.status()} ${r.url()}`)})
  page.on('requestfailed',r=>{if(!r.failure()?.errorText.includes('ERR_ABORTED'))failures.push(r.failure()?.errorText||r.url())})
  const datasets=await (await request.get('/api/v1/datasets')).json()
  const d=datasets.find((x:{active:boolean})=>x.active)
  expect(d.synthetic).toBe(false);expect(d.place_count).toBe(45858)
  await page.goto('/');await ready(page)
  const cards=page.locator('.ending-card')
  await expect(cards).toHaveCount(10)
  await expect(page.locator('.overview-coverage strong')).toHaveText('45.858')
  await expect(cards.locator('.card-count strong')).toHaveText(totals)
  expect(await page.locator('.maplibregl-map').count()).toBe(0)
  await expect(page.getByLabel('Farbmodus',{exact:true}).first()).toHaveValue('patterns')
  const positions=await cards.locator('.small-map').evaluateAll(nodes=>nodes.map(svg=>JSON.stringify(Array.from(svg.querySelectorAll('circle')).map(c=>[c.getAttribute('data-cell'),c.getAttribute('cx'),c.getAttribute('cy'),c.getAttribute('r')]))))
  expect(new Set(positions).size).toBe(1)
  await expect(cards.first().locator('circle')).toHaveCount(1062)
  expect(await cards.first().locator('path,polygon').count()).toBe(0)
  const viewboxes=await page.locator('.small-map').evaluateAll(es=>es.map(e=>e.getAttribute('viewBox')))
  expect(new Set(viewboxes).size).toBe(1)
  await visibleMaps(page)
  const localMaxima=await cards.locator('.color-range').evaluateAll(es=>es.map(e=>Number(e.getAttribute('data-maximum'))))
  expect(new Set(localMaxima).size).toBeGreaterThan(1)
  if(info.project.name==='desktop'){
    const layout=await cards.evaluateAll(es=>es.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})))
    expect(new Set(layout.map(b=>b.y)).size).toBe(2)
    expect(new Set(layout.map(b=>b.x)).size).toBe(5)
    expect(new Set(layout.map(b=>Math.round(b.height))).size).toBe(1)
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
  await page.screenshot({path:`artifacts/overview-${info.project.name}-real.png`,fullPage:true})
  await page.reload();await ready(page);await visibleMaps(page)
  const originalSize=page.viewportSize()!
  await page.setViewportSize({width:info.project.name==='mobile'?820:390,height:900})
  await ready(page);await visibleMaps(page)
  await page.setViewportSize(originalSize);await ready(page);await visibleMaps(page)

  const s=JSON.parse(new URL(page.url()).searchParams.get('s')!)
  const f={schema_version:1,dataset:d.id,regions:[],kinds:[],bbox:null,groups:s.endings.map((v:string,i:number)=>({id:`g${i}`,title:v,patterns:[{mode:'suffix',value:v}]}))}
  const q=JSON.stringify(f)
  const v=await (await request.get('/api/v1/grid/values',{params:{q}})).json()
  const target=v.cells.find((c:{counts:number[];denominator:number})=>c.counts[6]!>0&&c.denominator>=10)
  const names=await (await request.get(`/api/v1/grid/cells/${target.id}/places`,{params:{q,group:'g6',limit:8}})).json()
  expect(names.count).toBe(target.counts[6]);expect(names.denominator).toBe(target.denominator)
  expect(names.share).toBe(names.count/names.denominator)
  const node=cards.nth(6).locator(`circle[data-cell="${target.id}"]`)
  if(info.project.name==='mobile')await node.tap()
  else{
    await node.hover();await expect(page.locator('.cell-tooltip')).toContainText(names.items[0].name)
    await node.click()
  }
  await expect(page.getByRole('dialog',{name:'-bach',exact:true})).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText(names.items[0].name)
  await page.screenshot({path:`artifacts/overview-cell-${info.project.name}-real.png`,fullPage:true})
  await page.keyboard.press('Escape')

  await selectOverviewFilter(page,'Farbmodus','compare')
  await expect.poll(async()=>new Set(await cards.locator('.color-range').evaluateAll(es=>es.map(e=>e.getAttribute('data-maximum')))).size).toBe(1)
  const maximum=Math.max(...localMaxima)
  const shared=await cards.locator('.color-range').evaluateAll(es=>es.map(e=>Number(e.getAttribute('data-maximum'))))
  expect(shared).toEqual(Array(10).fill(maximum))
  await expect(page.locator('.shared-scale')).toContainText('gleiche Farbe, gleicher Anteil')
  await visibleMaps(page)
  // The same cell share on two cards must have exactly the same SVG fill.
  const fills=await cards.locator('circle[data-denominator]:not([data-denominator="0"])').evaluateAll(es=>es.map(e=>({share:Number(e.getAttribute('data-count'))/Number(e.getAttribute('data-denominator')),fill:e.getAttribute('fill')})))
  const byShare=new Map<number,string|null>()
  for(const cell of fills){if(byShare.has(cell.share))expect(cell.fill).toBe(byShare.get(cell.share));else byShare.set(cell.share,cell.fill)}
  await page.screenshot({path:`artifacts/overview-compare-${info.project.name}-real.png`,fullPage:true})

  await page.getByRole('button',{name:'Endung -by ändern',exact:true}).click()
  await page.locator('.ending-editor input').fill('ing')
  await page.getByLabel('Varianten (optional, eine pro Zeile)',{exact:true}).fill('ingen')
  await page.getByRole('button',{name:'Übernehmen',exact:true}).click();await ready(page)
  await expect(cards.last().locator('h2')).toHaveText('-ing')
  await expect(cards.last().locator('.card-variants')).toHaveText('auch -ingen')
  const changed=JSON.parse(new URL(page.url()).searchParams.get('s')!)
  expect(changed.variants[9]).toEqual(['ingen']);expect(changed.endings[1]).toBe('ingen')
  const filter=structuredClone(f);filter.groups[9]!.patterns=[{mode:'suffix',value:'ing'},{mode:'suffix',value:'ingen'}]
  const checked=await (await request.get('/api/v1/grid/values',{params:{q:JSON.stringify(filter)}})).json()
  await expect(cards.last().locator('.card-count strong')).toHaveText(checked.totals[9].toLocaleString('de-DE'))

  await selectOverviewFilter(page,'Region','state:01');await ready(page)
  await visibleMaps(page)
  const selected=await cards.locator('.color-range').evaluateAll(es=>es.map(e=>e.getAttribute('data-maximum')))
  expect(new Set(selected).size).toBe(1)
  const sharedUrl=page.url();await page.reload();await ready(page)
  await visibleMaps(page)
  await expect(page.getByLabel('Region',{exact:true}).first()).toHaveValue('state:01')
  await expect(page.getByLabel('Farbmodus',{exact:true}).first()).toHaveValue('compare')
  await expect(cards.last().locator('.card-variants')).toHaveText('auch -ingen')
  expect(new URL(page.url()).searchParams.get('s')).toBe(new URL(sharedUrl).searchParams.get('s'))
  expect(failures).toEqual([])
})
