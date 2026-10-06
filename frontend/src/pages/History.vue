<template>
  <div>
    <h1>消费履历</h1>
    <p class="muted">票面一经确认即冻结;列表与详情同一判定,只读不写回。</p>
    <p v-if="!rows.length" class="muted">暂无消费记录</p>
    <table v-else class="ticket">
      <thead><tr><th>#</th><th>时间</th><th>物品</th><th>数量</th><th>世代</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.id }}</td>
          <td class="nowrap">{{ r.created_at }}</td>
          <td>{{ r.item_name ?? '—' }}</td>
          <td>{{ r.qty ?? '—' }}</td>
          <td><span class="gen" :class="r.state">{{ label[r.state] }}</span></td>
          <td><router-link :to="'/consumptions/' + r.id">打开票面</router-link></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
const label = { frozen: '冻结世代', legacy: '旧世代', corrupt: '票面漂移' }
onMounted(async () => { rows.value = await api('/consumptions') })
</script>
