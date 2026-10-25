// Runs against the real nginx entry point. No mocks, imports or database writes.
import {chromium} from '@playwright/test'
import {mkdir,writeFile} from 'node:fs/promises'
import {pathToFileURL} from 'node:url'
import local from '../infra/local.json' with {type:'json'}

export async function inspectMaps(page){
  return page.locator('.ending-card').evaluateAll(cards=>cards.map(card=>{
    const svg=card.querySelector('svg.small-map'),stage=card.querySelector('.small-map-stage')
    const rect=e=>{const r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null}
    if(!svg)return {ending:card.dataset.ending,svg:false,stage:rect(stage),state:card.querySelector('.map-state')?.textContent}
    const box=svg.viewBox.baseVal,ctm=svg.getScreenCTM(),styles=getComputedStyle(svg)
    const circles=Array.from(svg.querySelectorAll('circle'))
    const measurements=circles.map(c=>{
      const raw=['cx','cy','r'].map(a=>c.getAttribute(a)),[x,y,r]=raw.map(Number)
      const finite=raw.every(v=>v!==null&&v.trim()!=='')&&[x,y,r].every(Number.isFinite)&&r>0
      const inside=finite&&x-r>=box.x&&x+r<=box.x+box.width&&y-r>=box.y&&y+r<=box.y+box.height
      const style=getComputedStyle(c),screen=rect(c)
      return {id:c.dataset.cell,raw,finite,inside,screen,
        visible:style.display!=='none'&&style.visibility==='visible'&&Number(style.opacity)>0&&style.fill!=='none',
        count:Number(c.dataset.count),denominator:Number(c.dataset.denominator),fill:style.fill}
    })
    return {ending:card.dataset.ending,svg:true,stage:rect(stage),size:rect(svg),viewbox:[box.x,box.y,box.width,box.height],
      matrix:ctm?[ctm.a,ctm.b,ctm.c,ctm.d,ctm.e,ctm.f]:null,
      styles:{display:styles.display,visibility:styles.visibility,opacity:styles.opacity,clipPath:styles.clipPath},
      circles:circles.length,finite:measurements.filter(c=>c.finite).length,inside:measurements.filter(c=>c.inside).length,
      visible:measurements.filter(c=>c.visible).length,matching:measurements.filter(c=>c.count>0).length,
      samples:measurements.filter((c,i)=>i<2||!c.finite||!c.inside).slice(0,5)}
  }))
}

// Read an actual browser screenshot, then count pixels with the computed fills
// of matching circles. A legend or a bare SVG cannot satisfy this check.
export async function paintedMap(page,svg,path){
  const colors=await svg.locator('circle').evaluateAll(nodes=>({
    all:Array.from(new Set(nodes.map(e=>getComputedStyle(e).fill))),
    matching:Array.from(new Set(nodes.filter(e=>Number(e.getAttribute('data-count'))>0).map(e=>getComputedStyle(e).fill)))
  }))
  const png=await svg.screenshot(path?{path}:{})
  return page.evaluate(async({src,colors})=>{
    const image=new Image();image.src=src;await image.decode()
    const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0)
    const palette=list=>new Set(list.map(color=>{ctx.fillStyle=color;ctx.fillRect(0,0,1,1);return Array.from(ctx.getImageData(0,0,1,1).data).slice(0,3).join(',')}))
    const expected=palette(colors.matching),all=palette(colors.all)
    ctx.drawImage(image,0,0)
    const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data
    let coloredPixels=0,circlePixels=0
    for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>0){
      const rgb=`${pixels[i]},${pixels[i+1]},${pixels[i+2]}`
      if(expected.has(rgb))coloredPixels++
      if(all.has(rgb))circlePixels++
    }
    return {width:canvas.width,height:canvas.height,coloredPixels,circlePixels}
  },{src:`data:image/png;base64,${png.toString('base64')}`,colors})
}

async function diagnose(){
  const report={url:`http://${local.host}:${local.nginxPort}`,console:[],requests:[],raster:[],errors:[]}
  const pending=[]
  let browser
  await mkdir('artifacts',{recursive:true})
  try{
    browser=await chromium.launch()
    const page=await browser.newPage({viewport:{width:1440,height:1100}})
    page.on('console',m=>{if(m.type()==='error'||m.type()==='warning')report.console.push({type:m.type(),text:m.text()})})
    page.on('pageerror',e=>report.errors.push(e.message))
    page.on('requestfailed',r=>report.requests.push({url:r.url(),error:r.failure()?.errorText}))
    page.on('response',r=>{
      if(r.status()>=400)report.requests.push({url:r.url(),status:r.status()})
      if(!/\/api\/v1\/grid\/(geometry|values)\?/.test(r.url()))return
      pending.push((async()=>{
        const body=await r.json()
        report.raster.push({url:r.url(),status:r.status(),headers:await r.allHeaders(),representation:body.representation,dataset:body.dataset,grid:body.grid,
          crs:body.crs,cell_size:body.cell_size,viewbox:body.viewbox,cells:body.cells?.length,
          denominator:body.denominator,totals:body.totals,samples:body.cells?.slice(0,3)})
      })().catch(e=>report.errors.push(e.message)))
    })
    page.on('framenavigated',frame=>{if(frame===page.mainFrame())(report.navigations??=[]).push(frame.url())})
    async function settled(){
      await page.waitForLoadState('networkidle')
      await page.waitForFunction(()=>document.querySelector('#overview')?.getAttribute('data-loaded')==='true'||!!document.querySelector('.error-panel'),{},{timeout:30000})
      await page.evaluate(()=>document.fonts.ready)
      await Promise.all(pending)
    }
    async function capture(label){
      await settled()
      const cards=await inspectMaps(page),paint=[]
      for(const [i,card] of cards.entries()){
        if(!card.svg||!card.size?.height||!card.size?.width)continue
        paint.push({ending:card.ending,...await paintedMap(page,page.locator('svg.small-map').nth(i))})
      }
      await page.evaluate(()=>scrollTo(0,0))
      await page.screenshot({path:`artifacts/maps-diagnosis-${label}.png`,fullPage:true})
      return {cards,paint,applicationError:await page.locator('.error-panel').allTextContents()}
    }
    await page.goto(report.url,{waitUntil:'networkidle'})
    report.desktop=await capture('desktop')
    await page.reload({waitUntil:'networkidle'})
    report.desktopReload=await capture('desktop-reload')
    await page.setViewportSize({width:390,height:844})
    report.mobileResize=await capture('mobile')
    await page.reload({waitUntil:'networkidle'})
    report.mobileReload=await capture('mobile-reload')
    report.summary=Object.fromEntries(['desktop','desktopReload','mobileResize','mobileReload'].map(key=>[key,{
      cards:report[key].cards.length,
      usable:report[key].cards.filter(c=>c.svg&&c.size.width>0&&c.size.height>0&&c.finite===c.circles&&c.inside===c.circles&&c.circles>0).length,
      painted:report[key].paint.filter(c=>c.circlePixels>10).length,
      matchingPixels:report[key].paint.map(c=>c.coloredPixels),errors:report[key].applicationError
    }]))
    if(Object.values(report.summary).some(s=>s.usable!==10||s.painted!==10||s.errors.length)||report.errors.length||report.console.some(m=>m.type==='error')||report.requests.some(r=>r.status>=400||(r.error&&!r.error.includes('ERR_ABORTED'))))process.exitCode=1
  }catch(e){report.errors.push(e.message);process.exitCode=1}
  finally{await browser?.close();await writeFile('artifacts/maps-diagnosis.json',JSON.stringify(report,null,2)+'\n')}
  console.log(JSON.stringify({url:report.url,summary:report.summary,errors:report.errors,console:report.console,requests:report.requests,report:'artifacts/maps-diagnosis.json'},null,2))
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await diagnose()
