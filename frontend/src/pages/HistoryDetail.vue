<template>
  <div>
    <h1>消费票面 #{{ props.id }}</h1>
    <p v-if="err" class="banner err">{{ err }}</p>
    <template v-if="d">
      <section class="gen">
        <h2>票面 · 冻结世代</h2>
        <template v-if="d.state === 'frozen'">
          <p>
            {{ d.ticket.item_name }} · 需求 {{ d.ticket.requested }}{{ d.ticket.unit }}
            · 当时 warn_days={{ d.ticket.warn_days }} · {{ d.ticket.created_at }}
          </p>
          <p v-if="d.ticket.note" class="muted">备注：{{ d.ticket.note }}</p>
          <table>
            <tr><th>批号</th><th>到期</th><th>取</th><th>扣后余量</th></tr>
            <tr v-for="x in d.ticket.deductions" :key="x.lot_id">
              <td>{{ x.lot_id }}</td><td>{{ x.expiry }}</td><td>{{ x.take }}</td><td>{{ x.remain_after }}</td>
            </tr>
          </table>
          <h3>当时在架余量快照</h3>
          <span v-for="s in d.ticket.shelf_after" :key="s.lot_id" class="lot">
            批号 {{ s.lot_id }} · {{ s.expiry }} · 余 {{ s.remain }}
          </span>
          <p v-if="!d.ticket.shelf_after.length" class="muted">当时该物品已取空</p>
        </template>
        <template v-else-if="d.state === 'legacy'">
          <p class="banner legacy">旧票 · 无快照：此行早于票面冻结，仅原样展示当时记录，不以当前在架补算、不回写。</p>
          <pre>{{ pretty(d.legacy) }}</pre>
        </template>
        <template v-else>
          <p class="banner drift">票面漂移：库中原文已损坏（{{ d.error }}）。以下为原样读出，未做任何修复写回。</p>
          <pre>{{ d.raw }}</pre>
        </template>
      </section>
      <section v-if="d.state === 'frozen'" class="gen live">
        <h2>当前在架 · 实时世代</h2>
        <p class="muted">以下为现时全层在架现算，与上方冻结票面分属不同世代，互不回写</p>
        <span v-for="x in live" :key="x.id" class="lot">{{ x.name }} ×{{ x.qty_remain }} · {{ x.expiry }}</span>
        <p v-if="!live.length" class="muted">当前该物品已无在架批次</p>
      </section>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const d = ref(null)
const live = ref([])
const err = ref('')
function pretty(x) { return JSON.stringify(x, null, 2) }
onMounted(async () => {
  try {
    d.value = await api('/consumptions/' + props.id)
    if (d.value.state === 'frozen') {
      const all = await api('/fridge')
      live.value = all.filter(x => x.item_id === d.value.ticket.item_id)
    }
  } catch (e) { err.value = e.message }
})
</script>
