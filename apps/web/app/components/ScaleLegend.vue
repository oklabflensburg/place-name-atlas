<script setup lang="ts">
import { percent,scaleGradient,zeroColor } from '~/utils/overview'
defineProps<{maximum:number|null}>()
</script>
<template>
  <div class="color-range" :data-maximum="maximum" :aria-label="maximum===null?'Farbskala wird geladen':`Farbskala 0 % bis ${percent(maximum,1)}`">
    <template v-if="maximum!==null&&maximum>0"><span class="color-ramp" :style="{background:scaleGradient}" /><div class="range-labels"><span>0 %</span><span>{{ percent(maximum/2,1) }}</span><span>{{ percent(maximum,1) }}</span></div></template>
    <span v-else-if="maximum===0" class="empty-scale"><i :style="{background:zeroColor}" />0 % · keine Treffer</span>
    <span v-else class="empty-scale">Wertebereich wird geladen …</span>
  </div>
</template>
