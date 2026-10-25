<script setup lang="ts">
import type { GridGeometry } from '@atlas/api-client'
import { cellColor, number, percent, suggestions, cleanEnding, normalizeEnding } from '~/utils/overview'
const props=defineProps<{id?:string;index:number;ending:string;variants:string[];geometry:GridGeometry|null;counts:Record<string,number>;denominators:Record<string,number>;total:number|null;denominator:number|null;maximum:number|null;busy:boolean;failed:boolean;failure?:string;highlighted?:boolean;last?:boolean}>()
const emit=defineEmits<{change:[value:string,variants:string[]];enlarge:[];remove:[];move:[direction:number];retry:[];inspect:[cell:string,pinned:boolean,event?:PointerEvent]}>()
const editing=ref(false),draft=ref(''),draftVariants=ref(''),invalid=ref('')
const input=ref<HTMLInputElement>()
async function edit(){draft.value=props.ending;draftVariants.value=props.variants.join('\n');editing.value=true;invalid.value='';await nextTick();input.value?.focus()}
function save(){
  try{
    const v=cleanEnding(draft.value)
    const variants=[...new Map(draftVariants.value.split('\n').filter(v=>v.trim()).map(v=>{const value=cleanEnding(v);return [normalizeEnding(value),value]})).values()].filter(value=>normalizeEnding(value)!==normalizeEnding(v))
    if(variants.length>7)throw new Error('Bitte höchstens sieben Varianten eingeben.')
    emit('change',v,variants);editing.value=false
  }catch(e){invalid.value=e instanceof Error?e.message:'Ungültige Endung.'}
}
const circles=computed(()=>props.geometry?.cells.map(c=>{
  const count=props.counts[c.id]??0,denominator=props.denominators[c.id]??0
  return {...c,count,denominator,fill:props.busy||props.failed?'#e4e7df':cellColor(count,denominator,props.maximum??0),
    label:`${number(count)} von ${number(denominator)} Orten · ${percent(count,denominator)}`}
})??[])
const titleId=computed(()=>props.id?`${props.id}-title`:`ending-${props.index}`)
</script>
<template>
  <article :id="id" class="ending-card" :class="{highlighted}" tabindex="-1" :aria-labelledby="titleId" :aria-busy="busy" :data-ending="ending">
    <header class="card-heading"><div><span class="card-index">{{ String(index+1).padStart(2,'0') }}</span><h2 :id="titleId" :title="`-${ending}`">-{{ ending }}</h2></div><button type="button" class="edit-ending" :aria-label="`Endung -${ending} ändern`" :aria-expanded="editing" :aria-controls="editing?`${titleId}-editor`:undefined" title="Endung und Reihenfolge ändern" @click="edit"><UIcon name="i-atlas-pencil" aria-hidden="true" /></button><button type="button" class="remove-ending" :aria-label="`Endung -${ending} entfernen`" title="Karte entfernen" @click="$emit('remove')"><UIcon name="i-atlas-close" aria-hidden="true" /></button></header>
    <p v-if="variants.length" class="card-variants" :title="variants.map(v=>`-${v}`).join(', ')">auch {{ variants.map(v=>`-${v}`).join(', ') }}</p>
    <form v-if="editing" :id="`${titleId}-editor`" class="ending-editor" @submit.prevent="save"><label :for="`edit-${index}`">Endung ändern</label><input :id="`edit-${index}`" ref="input" v-model="draft" list="ending-suggestions" maxlength="81" @keydown.esc="editing=false"><label :for="`variants-${index}`">Varianten (optional, eine pro Zeile)</label><textarea :id="`variants-${index}`" v-model="draftVariants" rows="3" @keydown.esc="editing=false" /><div><button type="submit">Übernehmen</button><button type="button" @click="editing=false">Abbrechen</button></div><p v-if="invalid" role="alert">{{ invalid }}</p><div class="card-order" aria-label="Kartenreihenfolge"><button type="button" :disabled="index===0" :aria-label="`-${ending} nach vorne verschieben`" @click="$emit('move',-1)"><UIcon class="order-previous" name="i-atlas-chevron-down" aria-hidden="true" />Nach vorne</button><button type="button" :disabled="last" :aria-label="`-${ending} nach hinten verschieben`" @click="$emit('move',1)">Nach hinten<UIcon class="order-next" name="i-atlas-chevron-down" aria-hidden="true" /></button></div></form>
    <p class="card-count"><template v-if="total!==null && !busy && !failed"><strong>{{ number(total) }}</strong> {{ total===1?'passender Ort':'passende Orte' }}</template><template v-else>{{ failed?'Daten nicht geladen': 'Wird geladen …' }}</template></p>
    <div v-if="failed&&failure" class="card-error" role="alert">{{ failure||'Kartendaten nicht verfügbar' }} <button @click="$emit('retry')">Erneut versuchen</button></div>
    <div class="small-map-stage">
      <svg v-if="geometry&&!failed" v-memo="[geometry,counts,denominators,maximum,busy,failed,ending]" class="small-map" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" :viewBox="geometry.viewbox.join(' ')" role="img" :aria-label="`Verteilung der Endung -${ending}. Zellwerte per Antippen oder über die Schaltfläche Zellwerte öffnen.`" @pointerleave="$emit('inspect','',false)">
        <circle v-for="c in circles" :key="c.id" :cx="c.cx" :cy="c.cy" :r="geometry.cell_size*.41" :data-cell="c.id" :data-denominator="c.denominator" :data-count="c.count" :fill="c.fill" stroke="transparent" stroke-width="1" vector-effect="non-scaling-stroke" :class="{'interactive-cell':!busy&&!failed}" @pointerenter="!busy&&!failed&&$emit('inspect',c.id,false,$event)" @click="!busy&&!failed&&$emit('inspect',c.id,true)"><title>{{ c.label }}</title></circle>
      </svg>
      <div v-else-if="busy" class="map-skeleton" aria-hidden="true"><span /></div>
      <span v-if="busy" class="map-state" role="status">Raster wird geladen …</span>
      <span v-else-if="failed||!geometry" class="map-state" role="status">Kartendaten nicht verfügbar</span>
      <span v-else-if="denominator===0" class="map-state" role="status">Keine erfassten Orte</span>
      <span v-else-if="total===0" class="map-state" role="status">Keine passenden Orte</span>
    </div>
    <ScaleLegend :maximum="busy||failed?null:maximum" />
    <footer class="card-actions"><button type="button" :disabled="busy||failed||!geometry" :aria-label="`Zellwerte für -${ending} öffnen`" @click="$emit('inspect',geometry?.cells.find(c=>(counts[c.id]??0)>0)?.id||geometry?.cells[0]?.id||'',true)">Zellwerte<UIcon name="i-atlas-info" aria-hidden="true" /></button><button type="button" :disabled="busy||failed||!geometry" :aria-label="`-${ending} vergrößern`" @click="$emit('enlarge')">Vergrößern<UIcon name="i-atlas-share" aria-hidden="true" /></button></footer>
  </article>
  <datalist v-if="index===0" id="ending-suggestions"><option v-for="s in suggestions" :key="s" :value="`-${s}`" /></datalist>
</template>
