import {selectOverviewFilter} from '../helpers/overview-controls'
import {test,expect,type Page} from '@playwright/test'
import {writeFile,mkdir} from 'node:fs/promises'
import {identities,matches} from '../../scripts/local-runtime.mjs'
const ready=async(page:Page)=>expect(page.locator('#overview')).toHaveAttribute('data-loaded','true')
async function add(page:Page,value:string,enter=true){await page.getByLabel('Endung hinzufügen',{exact:true}).fill(value);if(enter)await page.getByLabel('Endung hinzufügen',{exact:true}).press('Enter');else await page.getByRole('button',{name:'Hinzufügen',exact:true}).click()}

test('the twenty-six-card shared view explains sted matches and isolates the detail suffix',async({page})=>{
  const endings=['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by',
    'ing','burg','büttel','berg','rode','leben','büll','bek','tau','wald','weg','stadt','krug','rup','stedt','sted']
  const state={version:2,endings,region:'',kind:'',dataset:'bkg-2024-r3',variants:endings.map(()=>[]),
    mode:'patterns',grid:'laea-3035-square-20000-origin-0-v1'}
  await page.goto('/?s='+encodeURIComponent(JSON.stringify(state)));await ready(page)
  await expect(page.locator('.ending-card')).toHaveCount(26)
  const request=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/v1/places')
  await page.getByRole('button',{name:'-sted vergrößern',exact:true}).click()
  const filter=JSON.parse(new URL((await request).url()).searchParams.get('q')!)
  expect(filter.groups).toHaveLength(1)
  expect(filter.groups[0]).toMatchObject({id:'g25',patterns:[{mode:'suffix',value:'sted'}]})
  const detail=page.getByRole('dialog',{name:/-sted .*passende Orte/})
  const list=detail.locator('.detail-place-list button')
  await expect(list).toHaveCount(16)
  await expect(list.filter({hasText:'Silberstedt'})).toContainText('Treffer über „Sølvested“')
  const borgstedt=list.filter({hasText:'Borgstedt'})
  await expect(borgstedt).toContainText('Treffer über „Borgsted“')
  await borgstedt.click()
  await expect(detail.locator('.notice-panel')).toContainText('Borgstedt · Treffer über „Borgsted“')
})

test('free endings keep existing SVG nodes, reuse values, share order and support twenty cards',async({page,request},info)=>{
  const expected=identities('preview')
  for(const [path,identity] of [['/health/proxy',expected.nginx],['/health/instance',expected.api],['/health/web',expected.web]] as const)expect(matches(await (await request.get(path)).json(),identity)).toBe(true)
  const requests:{path:string;groups:string[];kinds:string[]}[]=[]
  page.on('request',r=>{const url=new URL(r.url());if(url.pathname.startsWith('/api/v1/grid/')){const f=JSON.parse(url.searchParams.get('q')||'{}');requests.push({path:url.pathname,groups:f.groups?.flatMap((g:{patterns:{value:string}[]})=>g.patterns.map(p=>p.value))??[],kinds:f.kinds??[]})}})
  await page.goto('/');await ready(page)
  const cards=page.locator('.ending-card')
  await expect(cards).toHaveCount(10)
  const reference=await cards.first().locator('svg').elementHandle(),originalTotal=await cards.first().locator('.card-count').textContent()
  const start=requests.length
  let release:()=>void=()=>{};const held=new Promise<void>(resolve=>release=resolve)
  await page.route('**/api/v1/grid/counts?*',async route=>{await held;await route.continue()})
  await add(page,'  -bek  ')
  await expect(cards).toHaveCount(11)
  await expect(cards.last()).toHaveAttribute('aria-busy','true')
  await expect(cards.first()).toHaveAttribute('aria-busy','false')
  await expect(cards.first().locator('.card-count')).toHaveText(originalTotal!)
  expect(await reference!.evaluate(node=>node.isConnected)).toBe(true)
  release();await ready(page);await page.unroute('**/api/v1/grid/counts?*')
  expect(requests.slice(start).map(r=>r.groups)).toEqual([['bek']])
  await page.screenshot({path:`artifacts/overview-eleventh-${info.project.name}.png`,fullPage:true})
  const duplicateStart=requests.length
  await add(page,'-BEK',false);await expect(cards).toHaveCount(11);await expect(cards.last()).toHaveClass(/highlighted/)
  expect(requests.length).toBe(duplicateStart)
  await add(page,' - ');await expect(page.locator('#ending-error')).toContainText('Bitte eine Endung eingeben')
  const localStart=requests.length
  await page.getByLabel('Endung -bek ändern',{exact:true}).click()
  await page.getByLabel('-bek nach vorne verschieben',{exact:true}).click()
  await page.getByRole('button',{name:'Abbrechen',exact:true}).click()
  await selectOverviewFilter(page,'Farbmodus','compare')
  await page.setViewportSize({width:820,height:920});await page.evaluate(()=>new Promise(requestAnimationFrame))
  expect(requests.length).toBe(localStart)
  await expect(cards.nth(9).locator('h2')).toHaveText('-bek')
  await page.getByLabel('Endung -bek entfernen',{exact:true}).click();await expect(cards).toHaveCount(10)
  expect(requests.length).toBe(localStart)
  await add(page,'bek');await ready(page);expect(requests.length).toBe(localStart)
  for(const suffix of ['burg','berg','büttel','büll','leben','rode','feld','hagen','stedt'])await add(page,suffix)
  await ready(page);await expect(cards).toHaveCount(20)
  const ordered=await cards.locator('h2').allTextContents(),link=page.url()
  await page.goto(link);await ready(page);await expect(cards.locator('h2')).toHaveText(ordered)
  await page.getByLabel('Endung -bek ändern',{exact:true}).click();await page.locator('.ending-editor input').fill('xyzneverexists');await page.getByRole('button',{name:'Übernehmen',exact:true}).click();await ready(page)
  await expect(page.locator('[data-ending=xyzneverexists]')).toContainText('Keine passenden Orte')
  await selectOverviewFilter(page,'Region','state:01');await ready(page)
  await selectOverviewFilter(page,'Ortsart','district');await ready(page)
  expect(new Set(await cards.locator('.color-range').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('data-maximum')))).size).toBe(1)
  await page.getByRole('button',{name:/Standardendungen wiederherstellen/}).click();await ready(page);await expect(cards).toHaveCount(10)
})

test('failure and late response affect only the requested card',async({page})=>{
  await page.goto('/');await ready(page)
  await page.route('**/api/v1/grid/counts?*',route=>route.fulfill({status:503,json:{message:'Gezielter Testausfall'}}))
  await add(page,'broken');await expect(page.locator('[data-ending=broken] .card-error')).toContainText('Gezielter Testausfall')
  await expect(page.locator('.ending-card[aria-busy=false] .card-count strong')).toHaveCount(10)
  await expect(page.locator('[data-ending=broken]')).not.toContainText('Keine passenden Orte')
  await page.unroute('**/api/v1/grid/counts?*');await page.locator('[data-ending=broken] .card-error button').click();await ready(page)
  let release:()=>void=()=>{};const held=new Promise<void>(resolve=>release=resolve)
  await page.route('**/api/v1/grid/counts?*',async route=>{const f=JSON.parse(new URL(route.request().url()).searchParams.get('q')!);if(f.kinds[0]==='settlement')await held;await route.continue().catch(()=>{})})
  await selectOverviewFilter(page,'Ortsart','settlement')
  await selectOverviewFilter(page,'Ortsart','district');await ready(page)
  const district=await page.locator('.overview-coverage strong').textContent();release();await page.waitForLoadState('networkidle')
  await expect(page.locator('.overview-coverage strong')).toHaveText(district!)
})

test('five browser runs record TTFB, transfer, JSON, SVG and paint boundaries separately',async({page},info)=>{
  const runs=[]
  for(let i=0;i<5;i++){
    await page.goto('/');await ready(page);await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
    runs.push(await page.evaluate(()=>({
      navigation:performance.getEntriesByType('navigation').map(n=>n.toJSON()),
      resources:(performance.getEntriesByType('resource') as PerformanceResourceTiming[]).filter(r=>r.name.includes('/api/v1/')).map(r=>({path:new URL(r.name).pathname,ttfb_ms:r.responseStart-r.requestStart,transfer_ms:r.responseEnd-r.responseStart,encoded_bytes:r.encodedBodySize,decoded_bytes:r.decodedBodySize,serverTiming:r.serverTiming.map(t=>({name:t.name,duration:t.duration}))})),
      processing:performance.getEntriesByType('measure').filter(m=>m.name.startsWith('atlas:')).map(m=>m.toJSON()),
      paint:performance.getEntriesByType('paint').map(p=>p.toJSON())
    })))
  }
  await mkdir('artifacts',{recursive:true});await writeFile(`artifacts/overview-browser-${info.project.name}.json`,JSON.stringify({cache:'Fresh page state per navigation; HTTP/backend caches warm after first run. Cold server requires a separate worker restart. SVG timing is Vue patch; paint-ready is a double-rAF boundary, not a rasterization trace.',runs},null,2))
})
