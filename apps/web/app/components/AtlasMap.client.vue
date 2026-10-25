<script setup lang="ts">
import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Map, CircleLayerSpecification, ExpressionSpecification } from 'maplibre-gl'
import type { Filter, PlaceOut } from '@atlas/api-client'

const props=defineProps<{ filter: Filter; center:[number,number]; zoom:number; places:PlaceOut[]; bounds?:[number,number,number,number] }>()
const emit=defineEmits<{ move:[center:[number,number],zoom:number]; select:[id:string]; failure:[message:string] }>()
const canvas=ref<HTMLDivElement>()
const zoomLevel=ref(props.zoom)
const ready=ref(false)
let styleReady=false
let map:Map|undefined
let observer:ResizeObserver|undefined
let boundaryController:AbortController|undefined
let boundaryDataset=''
const config=useRuntimeConfig()
maplibregl.setWorkerUrl(workerUrl)
const label= computed(() => zoomLevel.value<9 ? 'Kreise bündeln Orte nach Raster und Gruppenzugehörigkeit.' : 'Einzelne erfasste Orte. Farben zeigen Suchgruppen.')

function colors(): ExpressionSpecification {
  const values:unknown[]=['match',['get','mask']]
  for(let mask=1;mask<2**Math.max(1,props.filter.groups.length);mask++) {
    const hits=props.filter.groups.filter((_,i) => (mask & (1<<i))!==0)
    values.push(mask,hits.length>1?'#343c53':hits[0]?.color || '#126b61')
  }
  values.push('#126b61')
  return values as ExpressionSpecification
}
function updateSource() {
  if(!map || !styleReady || !props.filter.dataset) return
  ready.value=false
  if(boundaryDataset!==props.filter.dataset) {
    boundaryDataset=props.filter.dataset
    boundaryController?.abort();boundaryController=new AbortController()
    fetch(`/api/v1/boundaries?q=${encodeURIComponent(JSON.stringify({dataset:props.filter.dataset}))}`,{signal:boundaryController.signal})
      .then(r=>{if(!r.ok)throw new Error();return r.json()})
      .then(data=>{
        if(!map)return
        const boundaries=map.getSource('boundaries') as maplibregl.GeoJSONSource|undefined
        if(boundaries)boundaries.setData(data)
        else {
          map.addSource('boundaries',{type:'geojson',data})
          map.addLayer({id:'borders',type:'line',source:'boundaries',paint:{'line-color':'#a4b9ac','line-width':1}},map.getLayer('points')?'points':undefined)
        }
      }).catch(e=>{if(!(e instanceof DOMException && e.name==='AbortError'))emit('failure','Verwaltungsgrenzen konnten nicht geladen werden.')})
  }
  const source=map.getSource('places') as maplibregl.VectorTileSource|undefined
  const tiles=[`${location.origin}/api/v1/tiles/{z}/{x}/{y}.mvt?q=${encodeURIComponent(JSON.stringify(props.filter))}`]
  if(source) { source.setTiles(tiles); map.setPaintProperty('points','circle-color',colors()); return }
  map.addSource('places',{ type:'vector',tiles,minzoom:0,maxzoom:14 })
  map.addLayer({ id:'points',type:'circle',source:'places','source-layer':'places',paint:{
    'circle-color':colors(), 'circle-opacity':0.82,'circle-stroke-color':'#fff','circle-stroke-width':1.5,
    'circle-radius':['interpolate',['linear'],['get','count'],1,5,10,10,100,20,1000,30] } } as CircleLayerSpecification)
  map.on('click','points',e => {
    const feature=e.features?.[0]
    if(!feature) return
    if(Number(feature.properties?.count)>1) { map?.easeTo({center:e.lngLat,zoom:Math.min(14,(map?.getZoom()||5)+2)}); return }
    const id=feature.properties?.public_id
    if(typeof id==='string')emit('select',id)
  })
  map.on('mouseenter','points',()=>{if(map)map.getCanvas().style.cursor='pointer'})
  map.on('mouseleave','points',()=>{if(map)map.getCanvas().style.cursor=''})
}
onMounted(()=>{
  if(!canvas.value)return
  const sources:maplibregl.StyleSpecification['sources']={}
  const layers:maplibregl.StyleSpecification['layers']=[{id:'background',type:'background',paint:{'background-color':'#e8eeea'}}]
  if(config.public.basemapUrl && config.public.basemapAttribution) {
    sources.basemap={type:'raster',tiles:[config.public.basemapUrl],tileSize:256,attribution:config.public.basemapAttribution}
    layers.push({id:'basemap',type:'raster',source:'basemap'})
  }
  map=new maplibregl.Map({container:canvas.value,style:{version:8,sources,layers},center:props.center,zoom:props.zoom,maxZoom:14,
    attributionControl:{compact:false},localIdeographFontFamily:'sans-serif'})
  map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right')
  map.addControl(new maplibregl.ScaleControl({unit:'metric'}))
  if(props.bounds)map.fitBounds([[props.bounds[0],props.bounds[1]],[props.bounds[2],props.bounds[3]]],{padding:30,duration:0,maxZoom:12})
  map.on('load',()=>{styleReady=true;updateSource()})
  map.on('idle',()=>{ready.value=true})
  map.on('moveend',()=>{if(map){const c=map.getCenter().wrap();zoomLevel.value=map.getZoom();emit('move',[c.lng,c.lat],map.getZoom())}})
  map.on('error',()=>emit('failure','Eine Kartenkachel konnte nicht geladen werden. Filter eingrenzen oder erneut suchen; Liste und Auswertung bleiben verfügbar.'))
  map.getCanvas().setAttribute('aria-label','Ortsnamenkarte. Mit Pfeiltasten verschieben, mit Plus und Minus zoomen. Alle Orte auch in der Trefferliste.')
  observer=new ResizeObserver(()=>map?.resize())
  observer.observe(canvas.value)
})
watch(()=>props.filter,updateSource,{deep:true})
onBeforeUnmount(()=>{observer?.disconnect();boundaryController?.abort();map?.remove()})
</script>
<template>
  <div class="map-wrapper" :data-ready="ready">
    <div ref="canvas" class="map-canvas" />
    <div class="map-note"><span class="live-dot" />{{ label }}<br><small>Dunkle Punkte: Überschneidung mehrerer Gruppen. Hintergrund ohne externen Kartendienst.</small></div>
  </div>
</template>
