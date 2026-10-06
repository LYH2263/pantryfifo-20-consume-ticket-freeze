<template>
  <div>
    <h1>按临期消费</h1>
    <select v-model.number="item_id"><option v-for="i in items" :value="i.id">{{ i.name }}</option></select>
    <input type="number" v-model.number="qty" />
    <button @click="go">FEFO 扣减</button>
    <p v-if="err" class="drift">{{ err }}</p>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
const router = useRouter()
const items = ref([])
const item_id = ref(1)
const qty = ref(1)
const err = ref('')
onMounted(async () => { items.value = await api('/items'); if (items.value[0]) item_id.value = items.value[0].id })
async function go() {
  err.value = ''
  try {
    const r = await api('/consume', { method: 'POST', body: JSON.stringify({ item_id: item_id.value, qty: qty.value }) })
    router.push('/consumptions/' + r.id)
  } catch (e) { err.value = e.message }
}
</script>
