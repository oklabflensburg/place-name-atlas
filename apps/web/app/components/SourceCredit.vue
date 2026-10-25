<script setup lang="ts">
const props=defineProps<{text:string}>()
const parts=computed(()=>props.text.split(/(https?:\/\/[^\s]+)/g))
</script>
<template>
  <span class="source-credit"><template v-for="(part,i) in parts" :key="i"><a v-if="/^https?:\/\//.test(part)" :href="part">{{ part.endsWith('.pdf')?'Quellen-PDF ↗':'Quelle ↗' }}</a><template v-else>{{ part }}</template></template></span>
</template>
