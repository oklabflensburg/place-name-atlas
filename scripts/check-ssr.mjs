// Test the production server renderer entirely in-process; never open a socket.
// No browser, hydration, layout, accessibility or screenshot claims follow from it.
import {Server} from 'node:http'
import assert from 'node:assert/strict'
import {writeFile} from 'node:fs/promises'
async function verify(){
const listen=Server.prototype.listen
Server.prototype.listen=function(){return this}
globalThis._importMeta_={url:import.meta.url,env:process.env}
let runtime
try {runtime=await import('../apps/web/.output/server/chunks/nitro/nitro.mjs')}
finally {Server.prototype.listen=listen}
const useNitroApp=Object.values(runtime).find(v=>typeof v==='function'&&v.name==='useNitroApp')
assert.ok(useNitroApp,'Nitro app export must be available without relying on a generated alias')
const app=useNitroApp()
const index=await app.localFetch('/')
assert.equal(index.status,200)
const html=await index.text()
assert.equal((html.match(/class="ending-card"/g)||[]).length,10)
for(const suffix of ['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by'])assert.ok(html.includes(`data-ending="${suffix}"`))
assert.ok(html.includes('Endungssuche und gemeinsame Filter'))
assert.ok(!html.includes('class="filters"'))
assert.ok(html.includes('Muster hervorheben'))
assert.ok(html.includes('Anteile vergleichen'))
assert.equal((html.match(/class="overview-toolbar"/g)||[]).length,1)
assert.ok(!html.includes('class="add-endings"'))
assert.ok(!html.includes('class="shared-toolbar"'))
assert.ok(html.indexOf('id="custom-ending"')<html.indexOf('id="toolbar-region"'))
assert.ok(html.indexOf('id="toolbar-region"')<html.indexOf('id="toolbar-kind"'))
assert.ok(html.indexOf('id="toolbar-kind"')<html.indexOf('id="toolbar-mode"'))
assert.ok(html.includes('z. B. -bek'))
assert.ok(html.includes('Zurücksetzen: Standardendungen wiederherstellen'))
assert.ok(html.includes('>Zurücksetzen</span>'))
assert.ok(!html.includes('class="card-variants"'))
assert.ok(!html.includes('class="card-order"'))
assert.ok(html.includes('class="overview-color-ramp"'))
assert.ok(html.includes('Mehr Vorschläge'))
assert.equal((html.match(/<select /g)||[]).length,3)
assert.ok(!html.includes('Geteilte Ansichten sind auf'))
assert.equal((html.match(/data-suggestion=/g)||[]).length,4)
const health=await app.localFetch('/health/web')
assert.equal(health.status,200)
assert.equal(health.headers.get('cache-control'),'no-store')
assert.equal((await health.json()).service,'web')
const method=await app.localFetch('/methodik')
assert.equal(method.status,200)
const text=await method.text()
assert.ok(text.includes('20 × 20 km'))
assert.ok(text.includes('Kirchbach'))
assert.ok(text.includes('45.858'))
const report={execution:'Production Nuxt SSR through localFetch with the listener replaced by a no-op, no network or browser',index:200,serverRenderedCards:10,defaultEndings:10,method:200,tenCardsBeforeHydration:true,colorModesInInitialHTML:2,webHealthIdentity:200,combinedToolbar:1,inlineSuggestions:4,compactToolbarOrder:true,compactCardActions:true,emptyVariantRows:false,visibleResetLabel:"Zurücksetzen"}
await writeFile('docs/reports/grid-ssr-check.json',JSON.stringify(report,null,2)+'\n')
console.log(JSON.stringify(report))
}
verify().catch(error=>{console.error(error);process.exitCode=1})
