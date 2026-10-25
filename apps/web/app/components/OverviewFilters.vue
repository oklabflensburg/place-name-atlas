<script setup lang="ts">
import type {DatasetOut,RegionOut} from '@atlas/api-client'
import type {OverviewState} from '~/utils/overview'
type Field='region'|'kind'|'mode'|'dataset'
const state=defineModel<OverviewState>('state',{required:true})
const props=defineProps<{fields:Field[];idPrefix:string;regions:RegionOut[];datasets:DatasetOut[]}>()
const emit=defineEmits<{change:[field:Field]}>()
const kinds=[{value:'',label:'Alle Ortslagen',description:'Alle Ortslagen einschließlich Gemeindeteilen'},{value:'settlement',label:'Ortslagen ohne Gemeindeteile',description:'Ortslagen ohne Gemeindeteile'},{value:'district',label:'Gemeindeteile',description:'Gemeindeteile'}]
const modes=[{value:'patterns',label:'Muster hervorheben'},{value:'compare',label:'Anteile vergleichen'}]
const regionLabel=computed(()=>props.regions.find(r=>r.id===state.value.region)?.name||'Deutschland')
const datasetLabel=computed(()=>props.datasets.find(d=>d.id===state.value.dataset)?.label||'Angeforderter Stand nicht verfügbar')
</script>
<template>
  <template v-for="field in fields" :key="field">
    <div class="overview-filter" :class="`filter-${field}`">
      <label :for="`${idPrefix}-${field}`">{{ {region:'Region',kind:'Ortsart',mode:'Farbmodus',dataset:'Datenbestand'}[field] }}</label>
      <select v-if="field==='region'" :id="`${idPrefix}-${field}`" v-model="state.region" :title="regionLabel" @change="emit('change',field)">
        <option value="">Deutschland</option><option v-for="r in regions" :key="r.id" :value="r.id">{{ r.name }}{{ r.level==='district'?' · Kreis':'' }}</option>
      </select>
      <select v-else-if="field==='kind'" :id="`${idPrefix}-${field}`" v-model="state.kind" :title="kinds.find(k=>k.value===state.kind)?.description" :aria-describedby="`${idPrefix}-kind-description`" @change="emit('change',field)">
        <option v-for="kind in kinds" :key="kind.value" :value="kind.value">{{ kind.label }}</option>
      </select>
      <select v-else-if="field==='mode'" :id="`${idPrefix}-${field}`" v-model="state.mode" :title="modes.find(m=>m.value===state.mode)?.label" aria-describedby="scale-help" @change="emit('change',field)">
        <option v-for="mode in modes" :key="mode.value" :value="mode.value">{{ mode.label }}</option>
      </select>
      <select v-else :id="`${idPrefix}-${field}`" v-model="state.dataset" :title="datasetLabel" @change="emit('change',field)">
        <option v-if="state.dataset&&!datasets.some(d=>d.id===state.dataset)" :value="state.dataset">Angeforderter Stand nicht verfügbar</option>
        <option v-for="d in datasets" :key="d.id" :value="d.id">{{ d.label }}{{ d.active?'':' · historischer Stand' }}</option>
      </select>
      <span v-if="field==='kind'" :id="`${idPrefix}-kind-description`" class="sr-only">{{ kinds.find(k=>k.value===state.kind)?.description }}</span>
    </div>
  </template>
</template>
