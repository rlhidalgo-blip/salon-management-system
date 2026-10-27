import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { getManualSalesOptions } from './salesApi.js'

const decimal = /^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$/
const paper = /^PAPER-(\d{4})(\d{2})(\d{2})-(?!000)\d{3}$/
const peso = (cents) => `₱${(cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${(cents % 100n).toString().padStart(2, '0')}`

function cents(value) {
  if (!decimal.test(value)) return null
  const [whole, fraction = ''] = value.split('.')
  const amount = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0') || '0')
  return amount > 0n ? amount : null
}

function paperDate(reference) {
  const match = paper.exec(reference)
  if (!match) return null
  const day = `${match[1]}-${match[2]}-${match[3]}`
  const date = new Date(`${day}T00:00:00+08:00`)
  return !Number.isNaN(date.getTime()) && new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date) === day ? day : null
}

const blank = () => ({ occurrence: '', reference: '', items: [], payment: 'Cash',
  gcashReference: '', verified: false, kind: 'service', review: null, error: '' })

export default function ManualEntryForm({ user, disabled, active, resetToken, onSubmit, onRevalidateSession, onDraftChange }) {
  const [options, setOptions] = useState(null)
  const [loadState, setLoadState] = useState('loading')
  const [reload, setReload] = useState(0)
  const [draft, setDraft] = useState(blank)
  const nextLine = useRef(0)
  const submitting = useRef(false)
  const hasDraft = Boolean(draft.occurrence || draft.reference.trim() || draft.items.length ||
    draft.payment !== 'Cash' || draft.gcashReference.trim() || draft.verified || draft.review)
  useLayoutEffect(() => { onDraftChange?.(hasDraft) }, [hasDraft, onDraftChange])

  useEffect(() => {
    const controller = new AbortController()
    getManualSalesOptions(controller.signal).then((result) => {
      if (!controller.signal.aborted) { setOptions(result); setLoadState('ready') }
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) setLoadState(error.status === 403 ? 'forbidden' : 'error')
    })
    return () => controller.abort()
  }, [reload, onRevalidateSession])

  useEffect(() => { setDraft(blank()); nextLine.current = 0 }, [resetToken])

  function change(fields) { setDraft((old) => ({ ...old, ...fields, review: null, error: '' })) }
  function changeItem(line, fields) {
    setDraft((old) => ({ ...old, items: old.items.map((item) => item.line === line ? { ...item, ...fields } : item),
      review: null, error: '' }))
  }
  function addItem(choice) {
    if (disabled || draft.review) return
    setDraft((old) => ({ ...old, items: [...old.items, { line: ++nextLine.current,
      kind: old.kind, id: choice.id, staffId: '', originalName: '', price: '', commissionValue: '' }], error: '' }))
  }

  function prepareReview() {
    if (disabled) return
    const fail = (message) => setDraft((old) => ({ ...old, error: message }))
    const { occurrence, items, payment, gcashReference, verified } = draft
    const normalized = draft.reference.trim().toUpperCase()
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(occurrence) ||
        Number.isNaN(new Date(`${occurrence}:00+08:00`).getTime())) return fail('Enter the original Manila date and time.')
    const day = occurrence.slice(0, 10)
    if (paperDate(normalized) !== day) return fail('Use a valid PAPER-YYYYMMDD-NNN reference matching the original Manila date.')
    if (new Date(`${occurrence}:00+08:00`).getTime() > Date.now()) return fail('The original sale time cannot be in the future.')
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
    if (user.role !== 'Owner' && day < today) return fail('Previous-day Manual entries require Owner access.')
    if (!items.length) return fail('Add at least one service or product.')
    const requested = []
    const lines = []
    for (const item of items) {
      const catalog = (item.kind === 'service' ? options.services : options.products).find((row) => row.id === item.id)
      const staffId = item.staffId === '' ? null : Number(item.staffId)
      if (!catalog || (item.kind === 'service' && staffId === null) ||
          (staffId !== null && !options.staff.some((row) => row.id === staffId))) return fail('Select an existing credited Staff member for each Service.')
      const price = cents(item.price)
      if (!item.originalName.trim() || price === null) return fail('Enter the paper-verified original name and positive selling price for every item.')
      const type = item.kind === 'service' ? 'Percentage' : staffId !== null ? 'Fixed' : null
      const value = type === null ? null : cents(item.commissionValue)
      if (type !== null && (value === null || (type === 'Percentage' && value > 10000n) ||
          (type === 'Fixed' && value > price))) return fail('Enter a valid historical commission value for every credited item.')
      requested.push({ [item.kind === 'service' ? 'service_id' : 'product_id']: item.id,
        ...(staffId !== null ? { staff_id: staffId } : {}),
        item_name_snapshot: item.originalName.trim(), selling_price: item.price,
        ...(type !== null ? { commission_type_snapshot: type, commission_value_snapshot: item.commissionValue } : {}) })
      lines.push({ name: item.originalName.trim(), price, type, value: item.commissionValue,
        staff: options.staff.find((row) => row.id === staffId)?.name ?? 'No credited Staff' })
    }
    if (payment === 'GCash' && !gcashReference.trim()) return fail('Enter the GCash reference.')
    if (!verified) return fail('Confirm that the original paper record and historical values were verified.')
    const payload = { date_time: `${occurrence}:00+08:00`, manual_reference: normalized,
      verified_against_paper: true, payment_method: payment,
      ...(payment === 'GCash' ? { gcash_reference: gcashReference.trim() } : {}), items: requested }
    setDraft((old) => ({ ...old, error: '', review: { payload, lines,
      total: lines.reduce((sum, line) => sum + line.price, 0n) } }))
  }

  async function confirm() {
    if (disabled || submitting.current || !draft.review) return
    submitting.current = true
    try { await onSubmit(draft.review.payload) } finally { submitting.current = false }
  }

  if (loadState === 'loading') return <p role="status">Loading Manual options…</p>
  if (loadState !== 'ready') return <div role="alert"><p>{loadState === 'forbidden'
    ? 'You do not have permission to view Manual options.' : 'Manual options are unavailable. Try again.'}</p>
    <button type="button" onClick={() => { setLoadState('loading'); setReload((count) => count + 1) }}>Try again</button></div>

  const choices = draft.kind === 'service' ? options.services : options.products
  return <div className="sales-manual">
    <p className="sales-manual-note">Current names and active flags are reference choices only, not proof of historical validity. Verify against retained paper documentation.</p>
    {draft.review ? <section className="sales-surface sales-manual-review" aria-labelledby="manual-review-title">
      <h2 id="manual-review-title">Review Manual entry</h2>
      <dl className="sales-review-payment">
        <div><dt>Original Manila time</dt><dd>{draft.review.payload.date_time}</dd></div>
        <div><dt>Paper reference</dt><dd>{draft.review.payload.manual_reference}</dd></div>
      </dl>
      <ul className="sales-manual-review-items">{draft.review.lines.map((line, index) => <li key={index}>
        <div><strong>{line.name}</strong><span>{peso(line.price)}</span></div>
        <small>{line.staff} · {line.type ? `${line.type} ${line.value}${line.type === 'Percentage' ? '%' : ''}` : 'No Staff commission'}</small>
      </li>)}</ul>
      <div className="sales-review-total"><span>Gross Total <small>(provisional)</small></span><strong>{peso(draft.review.total)}</strong></div>
      <dl className="sales-review-payment"><div><dt>Payment Method</dt><dd>{draft.review.payload.payment_method}</dd></div>
        {draft.review.payload.payment_method === 'GCash' && <div><dt>GCash Reference</dt><dd>{draft.review.payload.gcash_reference}</dd></div>}
      </dl>
      <div className="sales-actions"><button type="button" disabled={disabled} onClick={() => setDraft((old) => ({ ...old, review: null }))}>Back</button>
        <button className="sales-primary" type="button" disabled={disabled} onClick={confirm}>Confirm Manual sale</button></div>
    </section> : <div className="sales-pos-grid">
      <section className="sales-surface sales-selection" aria-labelledby="manual-selection-title">
        <h2 id="manual-selection-title">Original sale</h2>
        <div className="sales-manual-fields">
          <label>Original Manila date and time<input type="datetime-local" value={draft.occurrence} disabled={disabled}
            onChange={(event) => change({ occurrence: event.target.value })} /></label>
          <label>Paper reference<input type="text" value={draft.reference} placeholder="PAPER-YYYYMMDD-NNN" disabled={disabled}
            onChange={(event) => change({ reference: event.target.value })} /></label>
        </div>
        <nav className="sales-tabs" aria-label="Manual item types">
          <button type="button" aria-pressed={draft.kind === 'service'} disabled={disabled} onClick={() => change({ kind: 'service' })}>Services</button>
          <button type="button" aria-pressed={draft.kind === 'product'} disabled={disabled} onClick={() => change({ kind: 'product' })}>Products</button>
        </nav>
        <div className="sales-catalog-list">{choices.length ? choices.map((choice) =>
          <button className="sales-catalog-item" type="button" key={`${draft.kind}-${choice.id}`} disabled={disabled}
            onClick={() => addItem(choice)} aria-label={`Add ${choice.name}${choice.active ? '' : ', Inactive now'}`}>
            <span>{choice.name}</span><span>{choice.active ? 'Active now' : 'Inactive now'}</span>
          </button>) : <p className="sales-empty">No existing {draft.kind}s are available.</p>}</div>
      </section>
      <section className="sales-surface sales-current" aria-labelledby="manual-current-title">
        <h2 id="manual-current-title">Manual sale items</h2>
        {!draft.items.length && <p className="sales-empty">No items added yet.</p>}
        {draft.items.map((item, index) => {
          const choice = (item.kind === 'service' ? options.services : options.products).find((row) => row.id === item.id)
          const type = item.kind === 'service' ? 'Percentage' : item.staffId ? 'Fixed' : null
          return <div className="sales-line" key={item.line}>
            <div className="sales-line-heading"><div><strong>{index + 1}. {choice?.name}</strong>
              <small>{item.kind === 'service' ? 'Service' : 'Product'} · one unit{choice?.active ? '' : ' · Inactive now'}</small></div>
              <button type="button" disabled={disabled} aria-label={`Remove Manual line ${index + 1}`}
                onClick={() => change({ items: draft.items.filter((row) => row.line !== item.line) })}>Remove</button></div>
            <div className="sales-manual-fields">
              <label>Credited Staff<select value={item.staffId} disabled={disabled} onChange={(event) => changeItem(item.line, { staffId: event.target.value, commissionValue: '' })}>
                <option value="">{item.kind === 'service' ? 'Select Staff' : 'No credited Staff'}</option>
                {options.staff.map((staff) => <option value={staff.id} key={staff.id}>{staff.name}{staff.active ? '' : ' (Inactive now)'}</option>)}
              </select></label>
              <label>Original item name<input type="text" value={item.originalName} disabled={disabled}
                onChange={(event) => changeItem(item.line, { originalName: event.target.value })} /></label>
              <label>Actual selling price<input type="text" inputMode="decimal" value={item.price} disabled={disabled}
                onChange={(event) => changeItem(item.line, { price: event.target.value })} /></label>
              {type && <><label>Historical commission type<input type="text" value={type} readOnly /></label>
                <label>Historical commission value<input type="text" inputMode="decimal" value={item.commissionValue} disabled={disabled}
                  onChange={(event) => changeItem(item.line, { commissionValue: event.target.value })} /></label></>}
            </div>
          </div>
        })}
        <div className="sales-payment"><label>Payment<select value={draft.payment} disabled={disabled}
          onChange={(event) => change({ payment: event.target.value, gcashReference: '' })}>
          <option value="Cash">Cash</option><option value="GCash">GCash</option></select></label>
          {draft.payment === 'GCash' && <label>GCash reference<input type="text" value={draft.gcashReference} disabled={disabled}
            onChange={(event) => change({ gcashReference: event.target.value })} /></label>}</div>
        <label className="sales-manual-attestation"><input type="checkbox" checked={draft.verified} disabled={disabled}
          onChange={(event) => change({ verified: event.target.checked })} />I verified the original paper record and historical item values against retained evidence.</label>
        {draft.error && <p className="sales-error" role="alert">{draft.error}</p>}
        <button className="sales-primary sales-review-button" type="button" disabled={disabled} onClick={prepareReview}>Review Manual sale</button>
      </section>
    </div>}
  </div>
}
