<template>
  <div>
    <h1>消费履历</h1>
    <p class="muted">票面自确认成功起冻结；旧票与漂移票原样展示，不做现算补写</p>
    <div v-for="r in rows" :key="r.id" class="hist-row" @click="$router.push('/history/' + r.id)">
      <span class="hid">#{{ r.id }}</span>
      <span class="htime">{{ r.created_at }}</span>
      <span v-if="r.state === 'frozen'">
        <span class="badge frozen">冻结票</span>{{ r.summary.item_name }} ×{{ r.summary.requested }}{{ r.summary.unit }}
      </span>
      <span v-else-if="r.state === 'legacy'"><span class="badge legacy">旧票 · 无快照</span>{{ r.note || '（无备注）' }}</span>
      <span v-else><span class="badge drift">票面漂移</span>{{ r.note || '（无备注）' }}</span>
    </div>
    <p v-if="!rows.length" class="muted">暂无消费记录</p>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await api('/consumptions') })
</script>
