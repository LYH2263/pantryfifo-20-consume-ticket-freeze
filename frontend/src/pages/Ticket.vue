<template>
  <div>
    <div v-if="d && d.state === 'corrupt'">
      <h1>票面漂移</h1>
      <p class="drift">该次消费履历已损坏(JSON 无法解析),以下为库中原文,原样读出;系统不会悄悄修复或写回。</p>
      <pre class="raw">{{ d.raw }}</pre>
      <p class="muted">当前在架数字属现世代,见「全层」。</p>
    </div>
    <div v-else-if="d && t">
      <h1>消费票面 #{{ d.id }}</h1>
      <p>
        <span class="gen" :class="d.state">
          {{ d.state === 'frozen' ? '票面世代 · 冻结于 ' + d.created_at : '旧世代票面 · 冻结前产生' }}
        </span>
      </p>
      <p v-if="d.state === 'legacy'" class="muted">
        该票产生于票面冻结之前,当时未记录余量快照,快照列以「无快照」标示;内容原样保留,不按现架现算补齐。
      </p>
      <table class="ticket">
        <tbody>
          <tr><th>物品</th><td>{{ t.item_name ?? '—' }}</td></tr>
          <tr><th>确认数量</th><td>{{ t.qty != null ? t.qty + (t.unit ? ' ' + t.unit : '') : '—' }}</td></tr>
          <tr><th>备注</th><td>{{ d.note || '—' }}</td></tr>
        </tbody>
      </table>
      <table class="ticket">
        <thead><tr><th>批号</th><th>到期</th><th>take</th><th>当时余量</th><th>临期(当时口径)</th></tr></thead>
        <tbody>
          <tr v-for="x in t.deductions" :key="x.lot_id">
            <td>#{{ x.lot_id }}</td>
            <td>{{ x.expiry ?? '—' }}</td>
            <td>{{ x.take }}</td>
            <td v-if="x.remain_before != null">{{ x.remain_before }} → {{ x.remain_after }}</td>
            <td v-else class="muted">无快照</td>
            <td>{{ warnLabel(x) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted">当前在架数字属现世代,见「全层」。</p>
    </div>
    <p v-else-if="err" class="drift">{{ err }}</p>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const d = ref(null)
const err = ref('')
const t = computed(() => d.value?.ticket)
function warnLabel(x) {
  const w = t.value?.warn_days
  if (w == null || !x.expiry) return '—'
  const days = Math.floor((new Date(x.expiry) - new Date(d.value.created_at.slice(0, 10))) / 86400000)
  if (days < 0) return '当时已过期'
  if (days <= w) return `当时临期 · 剩${days}天`
  return '—'
}
onMounted(async () => {
  try { d.value = await api('/consumptions/' + props.id) }
  catch (e) { err.value = e.message }
})
</script>
