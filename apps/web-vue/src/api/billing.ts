import api from './index'
import type { PricingRule } from '@/types'

export async function getPricing(): Promise<PricingRule[]> {
  const { data } = await api.get<PricingRule[]>('/api/billing/pricing')
  return data
}

export async function getBalance(): Promise<{
  balance: number
  daily_usage: number
  monthly_usage: number
}> {
  const { data } = await api.get('/api/billing/balance')
  return data
}

export async function deposit(
  amount: number,
  paymentMethod?: string
): Promise<any> {
  const { data } = await api.post('/api/payment/create', {
    amount,
    payment_method: paymentMethod || 'alipay',
  })
  return data
}

export async function getPlans(): Promise<any[]> {
  const { data } = await api.get('/api/payment/plans')
  return data
}

export async function getOrderStatus(orderNo: string): Promise<any> {
  const { data } = await api.get(`/api/payment/order/${orderNo}`)
  return data
}
