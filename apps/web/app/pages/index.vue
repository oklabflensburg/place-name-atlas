<script setup lang="ts">
import { api, type DatasetOut, type RegionOut, type GridGeometry, type CellPlaces, type PlacePage, type PlaceOut } from '@atlas/api-client'
import { defaultOverview,decodeOverview,encodeOverview,overviewFilter,alternativeMatchNames,number,percent,cleanEnding,normalizeEnding,scaleGradient,type OverviewState } from '~/utils/overview'
import {createOverviewLoader,commonKey,groupKey,Lru,type CardResult,type BaseData} from '~/utils/overviewLoader'
const route=useRoute(),router=useRouter()
const state=ref<OverviewState>(defaultOverview())
const datasets=ref<DatasetOut[]>([]),regions=ref<RegionOut[]>([])
const regionsError=ref('')
const geometry=shallowRef<GridGeometry|null>(null),shared=shallowRef<BaseData|null>(null)
const noticeIsError=ref(false),announcement=ref('')
const busy=ref(true),error=ref(''),notice=ref(''),inputError=ref(''),newEnding=ref(''),highlighted=ref('')
let nextCardId=10
const cardIds=ref(Array.from({length:10},(_,i)=>`card-${i}`))
type CardState={busy:boolean;error:string;result:CardResult|null}
const states=shallowReactive<Record<string,CardState>>({})
const dataset=computed(()=>datasets.value.find(d=>d.id===state.value.dataset))
const filter=computed(()=>overviewFilter(state.value))
function status(key:string){const full=commonKey(filter.value)+key;return states[full]??(states[full]=reactive({busy:true,error:'',result:null}))}
const cards=computed(()=>filter.value.groups.map(g=>status(groupKey(g))))
const values=computed(()=>shared.value?{denominator:shared.value.base.denominator,totals:cards.value.map(c=>c.result?.total??0)}:null)
const regionName=computed(()=>regions.value.find(r=>r.id===state.value.region)?.name||'Deutschland')
const regionChoices=computed(()=>regions.value.filter(r=>r.level!=='municipality'))
const sharedMaximum=computed(()=>Math.max(0,...cards.value.map(c=>c.result?.maximum??0)))
const colorMaximum=(i:number)=>cards.value[i]?.result?(state.value.mode==='patterns'?cards.value[i]!.result!.maximum:sharedMaximum.value):null
const loaded=computed(()=>!!geometry.value&&!!shared.value&&!busy.value&&!error.value&&cards.value.every(c=>!c.busy&&!c.error&&!!c.result))
function changeMode(){closeCell();syncUrl()}
let serial=0,controller:AbortController|undefined,initialized=false
let regionSerial=0,regionController:AbortController|undefined
const loader=createOverviewLoader()
const emptyCounts:Record<string,number>={}
const licenseUrl=(license:string)=>license==='CC-BY-4.0'?'https://creativecommons.org/licenses/by/4.0/':license==='dl-de/by-2-0'?'https://www.govdata.de/dl-de/by-2-0':null
function message(e:unknown){return e instanceof Error?e.message:'Die Anfrage ist fehlgeschlagen.'}
async function syncUrl(){if(!initialized)return false;try{await router.replace({query:{s:encodeOverview(state.value)}});return true}catch(e){noticeIsError.value=true;notice.value=message(e);return false}}
function recordRender(start:number,phase:string){
  nextTick(()=>{
    performance.measure(geometry.value?'atlas:svg-update':'atlas:values-ready',{start,end:performance.now(),detail:{phase}})
    if(geometry.value)requestAnimationFrame(()=>requestAnimationFrame(()=>performance.measure('atlas:paint-ready',{start,end:performance.now(),detail:{phase}})))
  })
}
async function loadEndings(only?:number){
  if(!shared.value||busy.value||!controller)return
  const current=serial,selected=structuredClone(filter.value),signal=controller.signal
  if(only!==undefined)selected.groups=[selected.groups[only]!]
  for(const g of selected.groups){const c=status(groupKey(g));c.busy=!c.result;c.error=''}
  await loader.groups(selected,shared.value,signal,(key,result,failure)=>{
    if(current!==serial||signal.aborted||!filter.value.groups.some(g=>groupKey(g)===key))return
    const started=performance.now(),c=status(key);c.result=result;c.error=failure?message(failure):'';c.busy=false
    recordRender(started,'counts')
  })
}
async function load(){
  controller?.abort();loader.abandon();controller=new AbortController();const current=++serial,signal=controller.signal
  busy.value=true;error.value='';shared.value=null;geometry.value=null;closeCell();closeDetail()
  // Only active filter/card states need to stay reactive. Results remain in the bounded loader cache.
  for(const key of Object.keys(states))delete states[key]
  const selected=structuredClone(filter.value)
  await syncUrl()
  if(current!==serial||signal.aborted)return
  try {
    await Promise.all([
      loader.common(selected,signal).then(data=>{if(current===serial){const started=performance.now();geometry.value=data.geometry;recordRender(started,'geometry')}}),
      loader.base(selected,signal).then(async data=>{
        if(current!==serial)return
        shared.value=data;busy.value=false
        // Counts need denominators, but do not wait for the slower geometry.
        await loadEndings()
      })
    ])
  }catch(e){if(current===serial&&!(e instanceof DOMException&&e.name==='AbortError')){controller?.abort();error.value=message(e);shared.value=null;geometry.value=null}}
  finally{if(current===serial)busy.value=false}
}
async function changeDataset(){state.value.region='';regions.value=[];await loadRegionsAndValues()}
async function loadRegionChoices(){
  regionController?.abort();regionController=new AbortController();const current=++regionSerial
  regionsError.value=''
  // Region choices are independent of map geometry, denominators and counts.
  // Fetch only the levels offered by the toolbar, without delaying the maps.
  await api('/api/v1/regions',{q:JSON.stringify({dataset:state.value.dataset}),scope:'overview'},{signal:regionController.signal})
    .then(r=>{if(current===regionSerial)regions.value=r})
    .catch(e=>{if(current===regionSerial&&!(e instanceof DOMException&&e.name==='AbortError'))regionsError.value=`Regionen konnten nicht geladen werden: ${message(e)}`})
}
async function loadRegionsAndValues(){await Promise.all([loadRegionChoices(),load()])}
async function highlight(index:number){
  highlighted.value=cardIds.value[index]!
  noticeIsError.value=false;notice.value=`Die Endung -${state.value.endings[index]} ist bereits vorhanden.`
  await nextTick();document.getElementById(cardIds.value[index]!)?.scrollIntoView({block:'nearest',behavior:'instant'});document.getElementById(cardIds.value[index]!)?.focus({preventScroll:true})
}
function duplicate(value:string,except=-1){return state.value.endings.findIndex((v,i)=>i!==except&&normalizeEnding(v)===normalizeEnding(value))}
function pruneStates(){const active=new Set(filter.value.groups.map(g=>commonKey(filter.value)+groupKey(g)));for(const key of Object.keys(states))if(!active.has(key))delete states[key]}
function addEnding(raw=newEnding.value){
  try{
    const value=cleanEnding(raw),existing=duplicate(value)
    inputError.value=''
    if(existing>=0){highlight(existing);return}
    const proposed={...state.value,endings:[...state.value.endings,value],variants:[...state.value.variants,[]]}
    encodeOverview(proposed);state.value=proposed;cardIds.value.push(`card-${nextCardId++}`);newEnding.value='';highlighted.value='';noticeIsError.value=false;notice.value='';announcement.value=`Karte -${value} hinzugefügt. ${state.value.endings.length} Karten in der Auswahl.`
    syncUrl();loadEndings(state.value.endings.length-1)
  }catch(e){inputError.value=message(e)}
}
function changeEnding(index:number,raw:string,variants:string[]){
  try{
    const value=cleanEnding(raw),existing=duplicate(value,index)
    if(existing>=0){highlight(existing);return}
    const proposed=JSON.parse(JSON.stringify(state.value));proposed.endings[index]=value;proposed.variants[index]=variants
    encodeOverview(proposed);state.value=proposed;pruneStates();closeCell();closeDetail();syncUrl();loadEndings(index)
  }catch(e){noticeIsError.value=true;notice.value=message(e)}
}
function removeEnding(index:number){state.value.endings.splice(index,1);state.value.variants.splice(index,1);cardIds.value.splice(index,1);pruneStates();closeCell();closeDetail();syncUrl()}
function moveEnding(index:number,direction:number){
  const target=index+direction;if(target<0||target>=state.value.endings.length)return
  for(const list of [state.value.endings,state.value.variants,cardIds.value]){const [item]=list.splice(index,1);(list as unknown[]).splice(target,0,item)}
  closeCell();closeDetail();syncUrl()
}
async function reset(){
  try{
  if(!datasets.value.length)datasets.value=await api('/api/v1/datasets')
  const defaults=defaultOverview();state.value.endings=defaults.endings;state.value.variants=defaults.variants;cardIds.value=defaults.endings.map(()=>`card-${nextCardId++}`)
  inputError.value='';notice.value='';noticeIsError.value=false;highlighted.value='';pruneStates();closeCell();closeDetail()
  if(!initialized||!dataset.value){state.value.dataset=datasets.value.find(d=>d.active)?.id??null;state.value.region='';initialized=true;await loadRegionsAndValues()}
  else{await syncUrl();await loadEndings()}
  }catch(e){error.value=message(e);busy.value=false}
}
async function share(){if(!await syncUrl())return;try{await navigator.clipboard.writeText(location.href);noticeIsError.value=false;notice.value='Link zur aktuellen Ansicht kopiert.'}catch{noticeIsError.value=true;notice.value='Der Link konnte nicht kopiert werden. Du kannst ihn aus der Adresszeile kopieren.'}}

const namesCache=new Lru<CellPlaces>(128)
const cell=ref(''),card=ref(0),pinned=ref(false),hover=ref(false),cellBusy=ref(false),cellError=ref('')
const cellPage=shallowRef<CellPlaces|null>(null),allNames=ref(false),cellOffset=ref(0)
const cellNamePreview=computed(()=>cellPage.value?.items.map(p=>p.matching_names.includes(p.name)?p.name:`${p.name} (${p.matching_names.join(', ')})`).join(' · '))
let cellController:AbortController|undefined,cellSerial=0,hoverTimer:ReturnType<typeof setTimeout>|undefined
const cellCount=computed(()=>cards.value[card.value]?.result?.counts[cell.value]??0)
const cellDenominator=computed(()=>shared.value?.denominators[cell.value]??0)
const cellChoices=computed(()=>geometry.value?.cells.map(c=>({id:c.id,count:cards.value[card.value]?.result?.counts[c.id]??0})).sort((a,b)=>b.count-a.count)||[])
function closeCell(){clearTimeout(hoverTimer);cellController?.abort();cellSerial++;pinned.value=false;hover.value=false;cell.value='';cellPage.value=null}
function inspect(index:number,id:string,lock:boolean,event?:PointerEvent){
  if(pinned.value)return
  clearTimeout(hoverTimer)
  if(!id){hoverTimer=setTimeout(()=>{hover.value=false},350);return}
  if(event?.pointerType==='touch'&&!lock)return
  const open=()=>{card.value=index;cell.value=id;pinned.value=lock;hover.value=!lock;allNames.value=false;cellOffset.value=0;fetchCell()}
  if(lock)open();else hoverTimer=setTimeout(open,220)
}
async function fetchCell(){
  cellController?.abort();cellController=new AbortController();const current=++cellSerial
  cellPage.value=null;cellBusy.value=true;cellError.value=''
  try{
    const g={...filter.value.groups[card.value]!,id:'cell'}
    const params={cell:cell.value,group:'cell',q:JSON.stringify({...filter.value,groups:[g]}),limit:allNames.value?50:8,offset:cellOffset.value}
    const key=JSON.stringify(params)
    const result=namesCache.get(key)??await api('/api/v1/grid/cells/{cell}/places',params,{signal:cellController.signal})
    namesCache.set(key,result);if(current===cellSerial)cellPage.value=result
  }
  catch(e){if(current===cellSerial && !(e instanceof DOMException&&e.name==='AbortError'))cellError.value=message(e)}
  finally{if(current===cellSerial)cellBusy.value=false}
}
function pin(){hover.value=false;pinned.value=true}
function keepHover(){clearTimeout(hoverTimer)}
function showAll(){allNames.value=true;cellOffset.value=0;pin();fetchCell()}
const detailIndex=ref<number|null>(null),detailPage=shallowRef<PlacePage|null>(null),detailBusy=ref(false),detailError=ref(''),detailOffset=ref(0),place=ref<PlaceOut|null>(null)
const detailFilter=computed(()=>({...filter.value,groups:detailIndex.value===null?[]:[filter.value.groups[detailIndex.value]!]}))
const detailCenter=computed<[number,number]>(()=>geometry.value?[(geometry.value.bounds[0]+geometry.value.bounds[2])/2,(geometry.value.bounds[1]+geometry.value.bounds[3])/2]:[10.25,51.2])
let detailController:AbortController|undefined,detailSerial=0
function closeDetail(){detailIndex.value=null;detailController?.abort();detailSerial++;detailPage.value=null;place.value=null}
async function openDetail(index:number){detailIndex.value=index;detailOffset.value=0;await loadDetail()}
async function loadDetail(){
  detailController?.abort();detailController=new AbortController();const current=++detailSerial
  detailBusy.value=true;detailError.value='';detailPage.value=null
  try{const p=await api('/api/v1/places',{q:JSON.stringify(detailFilter.value),limit:30,offset:detailOffset.value},{signal:detailController.signal});if(current===detailSerial)detailPage.value=p}
  catch(e){if(current===detailSerial&&!(e instanceof DOMException&&e.name==='AbortError'))detailError.value=message(e)}
  finally{if(current===detailSerial)detailBusy.value=false}
}
async function pickPlace(id:string){
  const current=detailSerial
  try{const result=await api('/api/v1/places/{id}',{id,q:JSON.stringify(detailFilter.value)},{signal:detailController?.signal});if(current===detailSerial&&detailIndex.value!==null)place.value=result}
  catch(e){if(current===detailSerial&&!(e instanceof DOMException&&e.name==='AbortError'))detailError.value=message(e)}
}
async function initialize(){
  try{
    if(!initialized&&typeof route.query.s==='string'){state.value=decodeOverview(route.query.s);cardIds.value=state.value.endings.map(()=>`card-${nextCardId++}`)}
    datasets.value=await api('/api/v1/datasets')
    if(!state.value.dataset)state.value.dataset=datasets.value.find(d=>d.active)?.id||null
    if(!state.value.dataset)throw new Error('Noch kein Datenbestand freigeschaltet. Bitte einen validierten GN250-/VG25-/VG250-EW-Import freischalten.')
    initialized=true;await loadRegionsAndValues()
  }catch(e){error.value=message(e);busy.value=false}
}
onMounted(initialize)
onBeforeUnmount(()=>{controller?.abort();regionController?.abort();closeCell();closeDetail()})
</script>
<template>
  <div class="atlas-app overview-app">
    <a class="skip-link" href="#overview">Zu den Karten</a>
    <header class="topbar"><NuxtLink to="/" class="brand" aria-label="Ortsnamenatlas Startseite"><span class="brand-mark" aria-hidden="true">ö</span><span>Ortsnamen<span class="brand-light">atlas</span><small>OK LAB FLENSBURG</small></span></NuxtLink><nav aria-label="Hauptnavigation"><span class="nav-active">Entdecken</span><NuxtLink :to="{path:'/methodik',query:route.query}">Daten &amp; Methodik</NuxtLink></nav><span class="header-note">NAMEN. MUSTER. REGIONEN.</span></header>
    <main class="overview-main">
      <div class="overview-intro"><div><h1>Wie Namen Landschaften prägen.</h1><p class="sr-only">Entdecke, wo Ortsnamen ähnliche Endungen tragen. Ein Kreis pro Zelle. Dunklere Kreise zeigen höhere Anteile.</p></div><span class="overview-coverage" aria-live="polite"><strong>{{ values?number(values.denominator):'–' }}</strong> erfasste Orte</span></div>
      <span class="sr-only" role="status">{{ announcement }}</span>
      <OverviewToolbar v-model:state="state" v-model:ending="newEnding" :datasets="datasets" :regions="regionChoices" :input-error="inputError" @add="addEnding" @region-change="load" @kind-change="load" @dataset-change="changeDataset" @mode-change="changeMode" @reset="reset" @share="share" />
      <div v-if="dataset?.synthetic" class="data-banner">Synthetische Testdaten · {{ dataset.scope }} · Keine Deutschlandauswertung</div>
      <div v-if="error" role="alert" class="error-panel">{{ error }} <button @click="initialized?loadRegionsAndValues():initialize()">Erneut versuchen</button></div>
      <div v-if="regionsError" role="alert" class="error-panel">{{ regionsError }} <button @click="loadRegionChoices">Regionen erneut laden</button></div>
      <div v-if="notice" class="toolbar-notice" :class="{'is-error':noticeIsError}" :role="noticeIsError?'alert':'status'"><span>{{ notice }}</span><button type="button" aria-label="Hinweis schließen" @click="notice=''"> <UIcon name="i-atlas-close" aria-hidden="true" /></button></div>
      <section class="shared-scale" aria-label="Farbskala">
        <div id="scale-help" class="scale-description"><strong>{{ state.mode==='patterns'?'Eigene Skala je Karte:':'Gemeinsame Anteilsskala:' }}</strong><span v-if="state.mode==='patterns'" class="overview-color-ramp" :style="{background:scaleGradient}" aria-hidden="true" /><span class="sr-only">{{ state.mode==='patterns'?'Jede Karte zeigt ihren eigenen numerischen Wertebereich unter der Karte.':'Gleiche Farben bedeuten in allen Karten gleiche Anteile.' }}</span></div>
        <ScaleLegend v-if="state.mode==='compare'" :maximum="busy||error?null:sharedMaximum" />
        <div class="scale-swatches"><span><i class="zero-swatch" aria-hidden="true" />0 % · kein Treffer</span><span><i class="no-data-swatch" aria-hidden="true" />Keine Daten</span></div>
        <NuxtLink class="scale-method" :to="{path:'/methodik',query:route.query}">Methodik<UIcon name="i-atlas-share" aria-hidden="true" /></NuxtLink>
      </section>
      <section id="overview" class="maps-grid" aria-label="Vergleichbare Endungskarten" :data-loaded="loaded" tabindex="-1">
        <EndingCard v-for="(ending,i) in state.endings" :id="cardIds[i]" :key="cardIds[i]" :index="i" :ending="ending" :variants="state.variants[i]!" :maximum="colorMaximum(i)" :geometry="geometry" :counts="cards[i]?.result?.counts??emptyCounts" :denominators="shared?.denominators??emptyCounts" :total="cards[i]?.result?.total??null" :denominator="shared?.base.denominator??null" :busy="!error&&(busy||!geometry||!!cards[i]?.busy)" :failed="!!error||!!cards[i]?.error" :failure="cards[i]?.error" :highlighted="highlighted===cardIds[i]" :last="i===state.endings.length-1" @change="(value,variants)=>changeEnding(i,value,variants)" @remove="removeEnding(i)" @move="moveEnding(i,$event)" @retry="shared?loadEndings(i):load()" @enlarge="openDetail(i)" @inspect="(id,lock,event)=>inspect(i,id,lock,event)" />
        <p v-if="!state.endings.length" class="notice-panel">Noch keine Karten. Füge eine Endung hinzu oder stelle die Standardauswahl wieder her.</p>
      </section>
      <footer class="overview-footer"><p>20 × 20 km · flächentreues Raster (EPSG:3035), als Kreise dargestellt · Literale Namensendungen, keine Herkunftszuordnung.<br>Inspiriert von <a href="https://github.com/moritzstefaner/ach-ingen-zell">Moritz Stefaner · -ach, -ingen, -zell</a>.<br>Redaktionelle Startauswahl. Endungen können sich überlappen; ihre Trefferzahlen werden nicht addiert.</p><NuxtLink :to="{path:'/methodik',query:route.query}">Daten &amp; Methodik ↗</NuxtLink><p class="credits"><template v-for="s in dataset?.sources" :key="s.product"><SourceCredit :text="s.attribution" /> · <a v-if="licenseUrl(s.license)" :href="licenseUrl(s.license)!">{{ s.license }}</a><span v-else>{{ s.license }}</span><br></template>Bearbeitung: Auswahl, Projektion, Rasterauswertung.</p></footer>
    </main>
    <aside v-if="hover&&!pinned&&cell" class="cell-tooltip" role="status" @pointerenter="keepHover" @pointerleave="hover=false" @keydown.esc="hover=false"><strong>-{{ state.endings[card] }} · Zelle {{ cell }}</strong><p>{{ number(cellCount) }} Treffer / {{ number(cellDenominator) }} Orte · <b>{{ percent(cellCount,cellDenominator) }}</b></p><p v-if="cellDenominator>0&&cellDenominator<10" class="low-count">Geringe Fallzahl: weniger als 10 Orte.</p><p v-if="!cellDenominator">Keine Daten: keine erfassten Orte in dieser Zelle.</p><p v-if="cellBusy">Ortsnamen werden geladen …</p><p v-else-if="cellError">{{ cellError }}</p><p v-else>{{ cellNamePreview||'Keine passenden Ortsnamen' }}<span v-if="cellPage&&cellPage.count>cellPage.items.length"> …</span></p><button @click="showAll">{{ cellCount>8?'Vollständige Trefferliste öffnen':'Zellinformation öffnen' }} ↗</button></aside>
    <AtlasDialog :open="pinned" labelledby="cell-title" @close="closeCell"><span class="eyebrow">RASTERZELLE · 20 × 20 KM</span><h2 id="cell-title">-{{ state.endings[card] }}</h2><label class="cell-select">Zelle auswählen<select v-model="cell" @change="cellOffset=0;fetchCell()"><option v-for="c in cellChoices" :key="c.id" :value="c.id">{{ c.id }} · {{ number(c.count) }} Treffer</option></select></label><p class="cell-ratio"><strong>{{ percent(cellCount,cellDenominator) }}</strong><br>{{ number(cellCount) }} Treffer / {{ number(cellDenominator) }} berücksichtigte Orte</p><p v-if="!cellDenominator">Keine Daten: Hier sind keine Orte erfasst.</p><p v-else-if="cellCount===0">0 % · Orte vorhanden, keine passenden Endungen.</p><p v-if="cellDenominator>0&&cellDenominator<10" class="low-count">Geringe Fallzahl: weniger als 10 Orte. Einzelne Treffer beeinflussen den Anteil stark.</p><p v-if="cellBusy" role="status">Ortsnamen werden geladen …</p><div v-else-if="cellError" role="alert">{{ cellError }} <button @click="fetchCell">Erneut versuchen</button></div><ul v-else class="cell-names"><li v-for="p in cellPage?.items" :key="p.id">{{ p.name }}<small v-if="!p.matching_names.includes(p.name)">Treffer über {{ p.matching_names.join(', ') }}</small></li></ul><button v-if="!allNames&&cellCount>8" class="primary-button" @click="showAll">Vollständige Trefferliste öffnen ({{ number(cellCount) }})</button><div v-if="allNames&&cellPage" class="pagination"><button :disabled="cellOffset===0||cellBusy" @click="cellOffset=Math.max(0,cellOffset-50);fetchCell()">← Zurück</button><span>{{ cellPage.count?cellOffset+1:0 }}–{{ Math.min(cellOffset+50,cellPage.count) }} / {{ number(cellPage.count) }}</span><button :disabled="cellOffset+50>=cellPage.count||cellBusy" @click="cellOffset+=50;fetchCell()">Weiter →</button></div><p class="method-note">Zähler und Nenner verwenden dieselben gemeinsamen Filter. Namensvarianten zählen je Ortsobjekt einmal.</p></AtlasDialog>
    <AtlasDialog :open="detailIndex!==null" labelledby="detail-title" wide @close="closeDetail"><template v-if="detailIndex!==null"><button class="back-overview" @click="closeDetail">← Zur Übersicht</button><h2 id="detail-title">-{{ state.endings[detailIndex] }} <small>{{ number(values?.totals[detailIndex]||0) }} passende Orte · {{ regionName }}</small></h2><p>Frei erkunden: Die Detailkarte zeigt Ortsobjekte als Punkte, bei kleinen Zoomstufen gebündelt. Die gemeinsame Anteilsdarstellung findest du in der Übersicht.</p><div class="expanded-map"><ClientOnly><AtlasMap :filter="detailFilter" :center="detailCenter" :zoom="5" :bounds="geometry?.bounds" :places="detailPage?.items||[]" @failure="detailError=$event" @select="pickPlace" /></ClientOnly></div><div v-if="detailError" role="alert" class="error-panel">{{ detailError }} <button @click="loadDetail">Trefferliste erneut laden</button></div><p v-if="place" class="notice-panel">{{ place.name }}<template v-if="alternativeMatchNames(place).length"> · Treffer über {{ alternativeMatchNames(place).map(name=>`„${name}“`).join(', ') }}</template> · {{ place.municipality?.name||'Gemeindezuordnung offen' }}<template v-if="place.municipality?.population"> · Gemeinde: {{ number(place.municipality.population) }} Einwohner ({{ place.municipality.population_date }})</template></p><h3>Trefferliste</h3><p v-if="detailBusy" role="status">Treffer werden geladen …</p><p v-if="detailPage?.total===0">Keine Treffer für diese Endung und die gewählten Filter.</p><div class="detail-place-list"><button v-for="p in detailPage?.items" :key="p.id" @click="place=p"><strong>{{ p.name }}</strong><small v-if="alternativeMatchNames(p).length" class="match-reason">Treffer über {{ alternativeMatchNames(p).map(name=>`„${name}“`).join(', ') }}</small><small>{{ p.regions.map(r=>r.name).join(' · ') }}</small></button></div><div v-if="detailPage" class="pagination"><button :disabled="detailOffset===0||detailBusy" @click="detailOffset=Math.max(0,detailOffset-30);loadDetail()">← Zurück</button><span>{{ detailPage.total?detailOffset+1:0 }}–{{ Math.min(detailOffset+30,detailPage.total) }} / {{ number(detailPage.total) }}</span><button :disabled="detailOffset+30>=detailPage.total||detailBusy" @click="detailOffset+=30;loadDetail()">Weiter →</button></div></template></AtlasDialog>
  </div>
</template>
