<template>
  <div>
    <h1>按临期消费</h1>
    <select v-model.number="item_id"><option v-for="i in items" :value="i.id">{{ i.name }}</option></select>
    <input type="number" v-model.number="qty" />
    <input v-model="note" placeholder="备注（随票冻结，可选）" />
    <button @click="go">FEFO 扣减</button>
    <p v-if="error" class="banner err">确认失败：{{ error }}（未生成任何票面）</p>
    <section v-if="ticket" class="gen">
      <h2>票面已冻结 · #{{ ticketId }}</h2>
      <p class="muted">{{ ticket.created_at }} · 当时 warn_days={{ ticket.warn_days }} · 此后入库与设置变更不再影响本票</p>
      <table>
        <tr><th>批号</th><th>到期</th><th>取</th><th>扣后余量</th></tr>
        <tr v-for="d in ticket.deductions" :key="d.lot_id">
          <td>{{ d.lot_id }}</td><td>{{ d.expiry }}</td><td>{{ d.take }}</td><td>{{ d.remain_after }}</td>
        </tr>
      </table>
      <router-link :to="'/history/' + ticketId">查看票面详情 →</router-link>
    </section>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const items = ref([])
const item_id = ref(1)
const qty = ref(1)
const note = ref('')
const ticket = ref(null)
const ticketId = ref(null)
const error = ref('')
onMounted(async () => { items.value = await api('/items'); if (items.value[0]) item_id.value = items.value[0].id })
async function go() {
  error.value = ''; ticket.value = null; ticketId.value = null
  try {
    const r = await api('/consume', { method: 'POST', body: JSON.stringify({ item_id: item_id.value, qty: qty.value, note: note.value }) })
    ticketId.value = r.id; ticket.value = r.ticket
  } catch (e) { error.value = e.message }
}
</script>
