<script setup lang="ts">
const props=defineProps<{open:boolean;labelledby:string;wide?:boolean}>()
const emit=defineEmits<{close:[]}>()
const element=ref<HTMLDialogElement>()
watch(()=>props.open,async open=>{
  await nextTick()
  if(open && !element.value?.open)element.value?.showModal()
  else if(!open && element.value?.open)element.value.close()
},{immediate:true})
</script>
<template>
  <dialog ref="element" :class="['atlas-dialog',{wide}]" :aria-labelledby="labelledby" @cancel.prevent="emit('close')" @click="($event.target===element)&&emit('close')">
    <div class="dialog-inner"><button class="dialog-close" aria-label="Schließen" @click="emit('close')">×</button><slot /></div>
  </dialog>
</template>
