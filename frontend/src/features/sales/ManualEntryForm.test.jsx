// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import ManualEntryForm from './ManualEntryForm.jsx'

const cashier = { id: 2, role: 'Cashier' }
const owner = { id: 1, role: 'Owner' }
const options = { staff: [{ id: 4, name: 'Ana', role: 'Stylist', active: false }],
  services: [{ id: 5, name: 'Current Cut', active: false }],
  products: [{ id: 7, name: 'Current Oil', active: true }] }
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })

function manilaMinute(daysAgo = 0) {
  const date = new Date(Date.now() - daysAgo * 86_400_000 - 60_000)
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date).replace(' ', 'T')
}

function fillTimeAndPaper(daysAgo = 0) {
  const occurrence = manilaMinute(daysAgo)
  fireEvent.change(screen.getByLabelText(/Original (Manila date and time|date & time \(Manila\))/), { target: { value: occurrence } })
  fireEvent.change(screen.getByLabelText('Paper reference'), { target: {
    value: ` paper-${occurrence.slice(0, 10).replaceAll('-', '')}-001 `,
  } })
  return occurrence
}

async function setup(user = cashier, onSubmit = vi.fn()) {
  render(<ManualEntryForm user={user} disabled={false} resetToken={0} onSubmit={onSubmit}
    onRevalidateSession={vi.fn().mockResolvedValue(true)} />)
  await screen.findByRole('button', { name: 'Add Current Cut, Inactive now' })
  return onSubmit
}

beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, options))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('loads minimal inactive options and requires historical inputs and attestation', async () => {
  const submit = await setup()
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/sales/manual-options')
  expect(fetch.mock.calls[0][1].credentials).toBe('same-origin')
  expect(screen.getByText(/do not prove past values/i)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Add Current Cut, Inactive now' }))
  expect(screen.getByText('Percentage commission from the original record')).toBeTruthy()
  expect(screen.queryByLabelText('Historical commission type')).toBeNull()
  expect(screen.getByLabelText('Name on paper').value).toBe('')
  expect(screen.getByLabelText('Price on paper').value).toBe('')
  expect(screen.getByLabelText('Commission rate (%)').value).toBe('')
  fillTimeAndPaper()
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/credited Staff/i)
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Name on paper'), { target: { value: 'Paper Cut' } })
  fireEvent.change(screen.getByLabelText('Price on paper'), { target: { value: '101.25' } })
  fireEvent.change(screen.getByLabelText('Commission rate (%)'), { target: { value: '50.00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/original paper record/i)
  fireEvent.click(screen.getByLabelText(/I verified the original paper record/i))
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByText('PAPER-' + manilaMinute().slice(0, 10).replaceAll('-', '') + '-001')).toBeTruthy()
  expect(screen.getByText('Paper Cut')).toBeTruthy()
  expect(screen.getByText(/Percentage 50.00%/)).toBeTruthy()
  expect(screen.getByText('Gross Total').parentElement.textContent).toContain('₱101.25')
  expect(submit).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  expect(submit.mock.calls[0][0]).toMatchObject({ verified_against_paper: true,
    payment_method: 'Cash', items: [{ service_id: 5, staff_id: 4,
      item_name_snapshot: 'Paper Cut', selling_price: '101.25',
      commission_type_snapshot: 'Percentage', commission_value_snapshot: '50.00' }] })
})

it('supports previous-day Owner entry, one unit per click, and GCash review', async () => {
  const submit = await setup(owner)
  const occurrence = fillTimeAndPaper(1)
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  const add = screen.getByRole('button', { name: 'Add Current Oil' })
  fireEvent.click(add)
  fireEvent.click(add)
  expect(screen.getAllByLabelText('Original item name')).toHaveLength(2)
  screen.getAllByLabelText('Original item name').forEach((field) => fireEvent.change(field, { target: { value: 'Old Oil' } }))
  screen.getAllByLabelText('Actual selling price').forEach((field) => fireEvent.change(field, { target: { value: '80.25' } }))
  fireEvent.change(screen.getByLabelText('Payment'), { target: { value: 'GCash' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/GCash reference/i)
  fireEvent.change(screen.getByLabelText('GCash reference'), { target: { value: ' synthetic-ref ' } })
  fireEvent.click(screen.getByLabelText(/I verified the original paper record/i))
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getAllByText('Old Oil')).toHaveLength(2)
  expect(screen.getByText('Gross Total').parentElement.textContent).toContain('₱160.50')
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  expect(submit.mock.calls[0][0]).toMatchObject({ date_time: `${occurrence}:00+08:00`,
    gcash_reference: 'synthetic-ref', items: [
      { product_id: 7, item_name_snapshot: 'Old Oil', selling_price: '80.25' },
      { product_id: 7, item_name_snapshot: 'Old Oil', selling_price: '80.25' },
    ] })
  expect(submit.mock.calls[0][0].items[0].commission_type_snapshot).toBeUndefined()
})

it('blocks Cashier previous-day entry and rejects invalid historical commission values', async () => {
  const submit = await setup()
  fillTimeAndPaper(1)
  fireEvent.click(screen.getByRole('button', { name: 'Add Current Cut, Inactive now' }))
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/Owner access/i)
  fillTimeAndPaper()
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Name on paper'), { target: { value: 'Old Cut' } })
  fireEvent.change(screen.getByLabelText('Price on paper'), { target: { value: '100.00' } })
  fireEvent.change(screen.getByLabelText('Commission rate (%)'), { target: { value: '100.01' } })
  fireEvent.click(screen.getByLabelText(/I verified the original paper record/i))
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/historical commission value/i)
  expect(submit).not.toHaveBeenCalled()
})

it('requires a valid paper date and supports credited Product Fixed policy', async () => {
  const submit = await setup(owner)
  const occurrence = fillTimeAndPaper()
  fireEvent.change(screen.getByLabelText('Paper reference'), { target: { value: 'PAPER-20260230-001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/valid PAPER/i)
  fireEvent.change(screen.getByLabelText('Paper reference'), { target: {
    value: `PAPER-${occurrence.slice(0, 10).replaceAll('-', '')}-001`,
  } })
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  fireEvent.click(screen.getByRole('button', { name: 'Add Current Oil' }))
  fireEvent.change(screen.getByLabelText('Credited Staff'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Original item name'), { target: { value: 'Paper Oil' } })
  fireEvent.change(screen.getByLabelText('Actual selling price'), { target: { value: '80.25' } })
  expect(screen.getByLabelText('Historical commission type').value).toBe('Fixed')
  fireEvent.change(screen.getByLabelText('Historical commission value'), { target: { value: '80.26' } })
  fireEvent.click(screen.getByLabelText(/I verified the original paper record/i))
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  expect(screen.getByRole('alert').textContent).toMatch(/historical commission value/i)
  fireEvent.change(screen.getByLabelText('Historical commission value'), { target: { value: '25.50' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  expect(submit.mock.calls[0][0].items[0]).toMatchObject({ product_id: 7, staff_id: 4,
    commission_type_snapshot: 'Fixed', commission_value_snapshot: '25.50' })
})
