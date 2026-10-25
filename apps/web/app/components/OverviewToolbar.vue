<script setup lang="ts">
import type {DatasetOut,RegionOut} from '@atlas/api-client'
import {normalizeEnding,number,suggestions,type OverviewState} from '~/utils/overview'
const state=defineModel<OverviewState>('state',{required:true})
const ending=defineModel<string>('ending',{required:true})
const props=defineProps<{datasets:DatasetOut[];regions:RegionOut[];inputError:string}>()
const emit=defineEmits<{add:[value:string];regionChange:[];kindChange:[];datasetChange:[];modeChange:[];reset:[];share:[]}>()
const endingInput=ref<HTMLInputElement>(),moreTrigger=ref<HTMLButtonElement>(),mobileTrigger=ref<HTMLButtonElement>()
const moreOpen=ref(false),mobileOpen=ref(false),suggestionsOpen=ref(false)
const mobileLayout=ref(false)
const featured=computed(()=>suggestions.filter(s=>['bek','büll','leben','rode'].includes(s)).slice(0,mobileLayout.value?3:4))
const remaining=computed(()=>suggestions.filter(s=>!featured.value.includes(s)))
const activeEndings=computed(()=>new Set(state.value.endings.map(normalizeEnding)))
const isActive=(value:string)=>activeEndings.value.has(normalizeEnding(value))
const dataset=computed(()=>props.datasets.find(d=>d.id===state.value.dataset))
const datasetSummary=computed(()=>{
  const d=dataset.value
  if(!d)return state.value.dataset?'Datenbestand nicht verfügbar':'Datenbestand wird geladen …'
  const publisher=d.label.split('·')[0]?.trim()||d.label
  return `${d.synthetic?'Testdaten':publisher} · ${d.geometry_date.slice(0,4)}`
})
const datasetDescription=computed(()=>dataset.value?`${dataset.value.label} · ${dataset.value.id}${dataset.value.active?' · aktueller Stand':' · historischer Stand'}`:state.value.dataset||'Datenbestand wird geladen')
const filterSummary=computed(()=>[
  props.regions.find(r=>r.id===state.value.region)?.name||(state.value.region||'Deutschland'),
  state.value.kind==='district'?'Gemeindeteile':state.value.kind==='settlement'?'Ortslagen ohne Gemeindeteile':'Alle Ortsarten'
].join(' · '))
function change(field:'region'|'kind'|'mode'|'dataset'){
  if(field==='region')emit('regionChange')
  else if(field==='kind')emit('kindChange')
  else if(field==='mode')emit('modeChange')
  else emit('datasetChange')
}
async function add(value=ending.value){
  const previous=state.value.endings.length
  emit('add',value)
  await nextTick()
  if(state.value.endings.length>previous)endingInput.value?.focus({preventScroll:true})
}
let suggestionChosen=false
function choose(value:string){suggestionChosen=true;suggestionsOpen.value=false;add(value)}
function suggestionCloseFocus(event:Event){if(suggestionChosen){event.preventDefault();suggestionChosen=false}}
function filterCloseFocus(event:Event,fromMobile:boolean){
  const previous=fromMobile?mobileTrigger.value:moreTrigger.value
  if(previous?.getClientRects().length)return
  const target=window.matchMedia('(max-width: 767px)').matches?mobileTrigger.value:moreTrigger.value
  if(target&&target.getClientRects().length){event.preventDefault();target.focus({preventScroll:true})}
}
const moreCloseFocus=(event:Event)=>filterCloseFocus(event,false)
const mobileCloseFocus=(event:Event)=>filterCloseFocus(event,true)
let media:MediaQueryList|undefined
function changeLayout(){
  const wasOpen=moreOpen.value||mobileOpen.value
  mobileLayout.value=media?.matches??false
  moreOpen.value=false;mobileOpen.value=false;suggestionsOpen.value=false
  if(wasOpen)nextTick(()=>{const target=media?.matches?mobileTrigger.value:moreTrigger.value;target?.focus({preventScroll:true})})
}
onMounted(()=>{media=window.matchMedia('(max-width: 767px)');mobileLayout.value=media.matches;media.addEventListener('change',changeLayout)})
onBeforeUnmount(()=>media?.removeEventListener('change',changeLayout))
</script>
<template>
  <section class="overview-toolbar" aria-label="Endungssuche und gemeinsame Filter">
    <div class="toolbar-primary">
      <form class="ending-entry" @submit.prevent="add()">
        <label for="custom-ending">Endung hinzufügen</label>
        <div class="ending-entry-controls"><input id="custom-ending" ref="endingInput" v-model="ending" placeholder="z. B. -bek" :aria-invalid="!!inputError" :aria-describedby="inputError?'ending-input-help ending-error':'ending-input-help'" autocomplete="off" spellcheck="false"><button type="submit" class="toolbar-button toolbar-add"><UIcon name="i-atlas-plus" aria-hidden="true" />Hinzufügen</button></div>
        <span id="ending-input-help" class="sr-only">Namensendung mit oder ohne führenden Bindestrich. Mit Enter hinzufügen.</span>
        <p v-if="inputError" id="ending-error" class="ending-input-error" role="alert">{{ inputError }}</p>
      </form>
      <div class="toolbar-visible-filters"><OverviewFilters v-model:state="state" :fields="['region','kind','mode']" id-prefix="toolbar" :regions="regions" :datasets="datasets" @change="change" /></div>
      <div class="toolbar-more-filters">
        <UPopover v-model:open="moreOpen" :content="{align:'end',onCloseAutoFocus:moreCloseFocus}" :ui="{content:'toolbar-filter-popover'}">
          <button ref="moreTrigger" type="button" class="toolbar-button toolbar-secondary" :class="{'is-open':moreOpen}" :aria-expanded="moreOpen"><UIcon name="i-atlas-sliders" aria-hidden="true" />Weitere Filter</button>
          <template #content><div class="toolbar-filter-content"><h2>Weitere Filter</h2><OverviewFilters v-model:state="state" :fields="['dataset']" id-prefix="additional" :regions="regions" :datasets="datasets" @change="change" /><p>Der Datenbestand gilt für alle Karten.</p></div></template>
        </UPopover>
      </div>
      <div class="toolbar-mobile-filters">
        <UModal v-model:open="mobileOpen" title="Filter" description="Änderungen gelten sofort für alle Karten." :transition="false" :content="{onCloseAutoFocus:mobileCloseFocus}" :ui="{content:'toolbar-mobile-dialog',header:'toolbar-dialog-header',body:'toolbar-dialog-body',footer:'toolbar-dialog-footer'}">
          <button ref="mobileTrigger" type="button" class="toolbar-button toolbar-secondary" :class="{'is-open':mobileOpen}" :aria-expanded="mobileOpen"><UIcon name="i-atlas-sliders" aria-hidden="true" />Filter</button>
          <template #close><button type="button" class="toolbar-close" aria-label="Filter schließen"><UIcon name="i-atlas-close" aria-hidden="true" /></button></template>
          <template #body><OverviewFilters v-model:state="state" :fields="['region','kind','mode','dataset']" id-prefix="mobile" :regions="regions" :datasets="datasets" @change="change" /></template>
          <template #footer><button type="button" class="toolbar-button toolbar-add" @click="mobileOpen=false">Fertig</button></template>
        </UModal>
      </div>
      <p class="toolbar-mobile-summary">{{ filterSummary }}</p>
    </div>
    <div class="toolbar-secondary-row">
      <div class="ending-chips" aria-label="Vorgeschlagene Endungen"><span>Vorschläge:</span>
        <button v-for="s in featured" :key="s" type="button" :data-suggestion="s" :data-active="isActive(s)" :class="{'is-active':isActive(s)}" :title="isActive(s)?`Vorhandene Karte -${s} anzeigen`:`Endung -${s} hinzufügen`" @click="add(s)">-{{ s }}<UIcon v-if="isActive(s)" name="i-atlas-check" aria-hidden="true" /><span v-if="isActive(s)" class="sr-only"> (bereits vorhanden)</span></button>
        <UPopover v-if="remaining.length" v-model:open="suggestionsOpen" :content="{align:'start',onCloseAutoFocus:suggestionCloseFocus}" :ui="{content:'toolbar-suggestions-popover'}">
          <button type="button" class="suggestions-more" aria-label="Mehr Vorschläge" title="Mehr Vorschläge" :aria-expanded="suggestionsOpen"><UIcon name="i-atlas-more" aria-hidden="true" /></button>
          <template #content><div class="more-ending-chips"><h2>Weitere Vorschläge</h2><div class="ending-chips"><button v-for="s in remaining" :key="s" type="button" :data-suggestion="s" :data-active="isActive(s)" :class="{'is-active':isActive(s)}" :title="isActive(s)?`Vorhandene Karte -${s} anzeigen`:`Endung -${s} hinzufügen`" @click="choose(s)">-{{ s }}<UIcon v-if="isActive(s)" name="i-atlas-check" aria-hidden="true" /><span v-if="isActive(s)" class="sr-only"> (bereits vorhanden)</span></button></div></div></template>
        </UPopover>
      </div>
      <div class="toolbar-context"><span class="toolbar-dataset" :title="datasetDescription">{{ datasetSummary }}<span v-if="dataset&&!dataset.active" class="historical-dataset"> · Historischer Stand</span></span><span class="toolbar-card-count">{{ number(state.endings.length) }} {{ state.endings.length===1?'Karte':'Karten' }}</span></div>
      <div class="toolbar-actions"><button type="button" class="toolbar-button toolbar-reset" aria-label="Zurücksetzen: Standardendungen wiederherstellen" aria-describedby="reset-scope" title="Standardendungen wiederherstellen. Region, Ortsart, Datenbestand und Farbmodus bleiben erhalten." @click="emit('reset')"><UIcon name="i-atlas-reset" aria-hidden="true" /><span>Zurücksetzen</span></button><span id="reset-scope" class="sr-only">Stellt die Standardendungen wieder her. Region, Ortsart, Datenbestand und Farbmodus bleiben erhalten.</span><button type="button" class="toolbar-button toolbar-secondary toolbar-share" @click="emit('share')">Ansicht teilen<UIcon name="i-atlas-share" aria-hidden="true" /></button></div>
    </div>
  </section>
</template>
