import api from './index'
import type { PaymentOrderListResponse, PricingRule } from '@/types'

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
): Promise<{
  order_no: string
  amount: number
  status: string
  payment_url?: string
}> {
  const { data } = await api.post<{
    order_no: string
    amount: number
    status: string
    payment_url?: string
  }>('/api/payment/create', {
    type: 'RECHARGE',
    amount,
    payment_method: paymentMethod || 'alipay',
  })
  return data
}

export async function getPaymentOrders(page = 1, pageSize = 20): Promise<PaymentOrderListResponse> {
  const { data } = await api.get<PaymentOrderListResponse>('/api/payment/orders', {
    params: { page, page_size: pageSize },
  })
  return data
}
