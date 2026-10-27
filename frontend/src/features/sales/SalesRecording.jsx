import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { getSalesOptions } from './salesApi.js'
import ManualEntryForm from './ManualEntryForm.jsx'
import OwnerSaleReconciliation from './OwnerSaleReconciliation.jsx'
import './SalesRecording.css'

const pricePattern = /^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$/
const money = (cents) => `₱${(cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${(cents % 100n).toString().padStart(2, '0')}`
function peso(value) {
  const raw = String(value)
  if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) return '—'
  const [whole, fraction = ''] = raw.split('.')
  return `₱${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`
}
function priceCents(raw) {
  if (!pricePattern.test(raw)) return null
  const [whole, fraction = ''] = raw.split('.')
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0') || '0')
  return cents > 0n ? cents : null
}

export default function SalesRecording({ user, csrfToken, onRevalidateSession, pendingSale, onDraftChange }) {
  const [mode, setMode] = useState('direct')
  const [manualVisited, setManualVisited] = useState(false)
  const [manualReset, setManualReset] = useState(0)
  const [submittedMode, setSubmittedMode] = useState('direct')
  const [options, setOptions] = useState(null)
  const [loadState, setLoadState] = useState('loading')
  const [reload, setReload] = useState(0)
  const [items, setItems] = useState([])
  const [kind, setKind] = useState('service')
  const [search, setSearch] = useState('')
  const [payment, setPayment] = useState('Cash')
  const [reference, setReference] = useState('')
  const [review, setReview] = useState(null)
  const [manualDraft, setManualDraft] = useState(false)
  const [formError, setFormError] = useState('')
  const nextLine = useRef(0)
  const submitting = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    getSalesOptions(controller.signal).then((result) => {
      if (controller.signal.aborted) return
      setOptions(result)
      setLoadState('ready')
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Retry remains available. */ }
      }
      setFormError(error.status === 403 ? 'You do not have permission to record sales.' : 'Sales options are unavailable. Try again.')
      setLoadState('error')
    })
    return () => controller.abort()
  }, [reload, onRevalidateSession])

  const locked = pendingSale.blocked || Boolean(pendingSale.pending) || pendingSale.working
  const confirmed = !pendingSale.pending && Boolean(pendingSale.sale)
  const directDraft = items.length > 0 || payment !== 'Cash' || reference.trim() !== '' || Boolean(review)
  const hasUnsentDraft = confirmed
    ? (submittedMode === 'direct' ? manualDraft : directDraft)
    : directDraft || manualDraft
  useLayoutEffect(() => { onDraftChange?.(hasUnsentDraft) }, [hasUnsentDraft, onDraftChange])
  const sameUser = pendingSale.pending?.userId === user.id
  const choices = kind === 'service' ? options?.services ?? [] : options?.products ?? []
  const visibleChoices = choices.filter((item) => item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  const provisional = items.reduce((total, item) => {
    const cents = priceCents(item.price)
    return total === null || cents === null ? null : total + cents
  }, 0n)

  function addItem(item) {
    if (locked || review || !choices.some((choice) => choice.id === item.id)) return
    setItems((old) => [...old, { line: ++nextLine.current, kind, itemId: item.id,
      staffId: '', price: item.current_price }])
    setFormError('')
  }

  function updateItem(line, change) {
    setItems((old) => old.map((item) => item.line === line ? { ...item, ...change } : item))
    setFormError('')
  }

  function prepareReview() {
    if (locked) return
    if (items.length === 0) return setFormError('Add at least one service or product.')
    const lines = []
    const requested = []
    for (const item of items) {
      const catalog = (item.kind === 'service' ? options.services : options.products)
        .find((choice) => choice.id === item.itemId)
      const staffId = item.staffId === '' ? null : Number(item.staffId)
      const staff = options.staff.find((member) => member.id === staffId)
      if (!catalog || (item.kind === 'service' && !staff) || (staffId !== null && !staff)) {
        return setFormError('Select active Staff for each Service and any credited Product.')
      }
      const cents = priceCents(item.price)
      if (cents === null || (!(item.kind === 'service' && catalog.allows_variable_price) &&
          cents !== priceCents(catalog.current_price))) {
        return setFormError('Check selling prices. Only variable-price Services may change price.')
      }
      requested.push({ [item.kind === 'service' ? 'service_id' : 'product_id']: catalog.id,
        ...(staffId !== null ? { staff_id: staffId } : {}), selling_price: item.price })
      lines.push({ name: catalog.name, staff: staff?.name ?? 'No credited Staff', cents })
    }
    if (payment === 'GCash' && !reference.trim()) return setFormError('Enter the GCash reference.')
    const payload = { payment_method: payment,
      ...(payment === 'GCash' ? { gcash_reference: reference.trim() } : {}), items: requested }
    setReview({ payload, lines, total: lines.reduce((sum, line) => sum + line.cents, 0n) })
    setFormError('')
  }

  async function confirm() {
    if (submitting.current || !review || locked) return
    submitting.current = true
    setSubmittedMode('direct')
    try { await pendingSale.submit(review.payload, csrfToken, 'direct') } finally { submitting.current = false }
  }

  async function confirmManual(payload) {
    setSubmittedMode('manual')
    return pendingSale.submit(payload, csrfToken, 'manual')
  }

  function newSale() {
    if (!pendingSale.startNewSale()) return
    if (submittedMode === 'manual') setManualReset((old) => old + 1)
    else {
      setItems([])
      setKind('service')
      setSearch('')
      setPayment('Cash')
      setReference('')
      setReview(null)
      setFormError('')
      nextLine.current = 0
    }
  }

  if (mode === 'direct' && !confirmed && loadState === 'loading' && !manualVisited) {
    return <section className="sales-recording"><p role="status">Loading sales options…</p></section>
  }
  return <section className="sales-recording" aria-labelledby={confirmed ? 'sales-confirmed-title' : 'sales-title'}>
    {confirmed ? <div className="sales-result" role="status">
      <div className="sales-result-heading">
        <svg className="sales-success-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" />
        </svg>
        <h1 id="sales-confirmed-title">Sale Confirmed</h1>
        <p>Transaction #{pendingSale.sale.id}</p>
      </div>
      <dl className="sales-summary">
        <div><dt>Payment Method</dt><dd>{pendingSale.sale.payment_method}</dd></div>
        <div className="sales-summary-gross"><dt>Gross Sales</dt><dd>{peso(pendingSale.sale.gross_sales)}</dd></div>
        <div><dt>Staff Commission</dt><dd>{peso(pendingSale.sale.total_staff_commission)}</dd></div>
        <div><dt>Business Share</dt><dd>{peso(pendingSale.sale.total_business_share)}</dd></div>
      </dl>
      {pendingSale.blocked && <p className="sales-error" role="alert">{pendingSale.error}</p>}
      <button className="sales-primary" type="button" disabled={pendingSale.blocked || pendingSale.working}
        onClick={newSale}>New Sale</button>
    </div> : <>
    <div className="sales-heading"><h1 id="sales-title">Sales Recording</h1>
      <p>{mode === 'direct' ? 'Record a completed, current-day sale. Each line is one unit.'
        : 'Enter a paper-verified original sale. Each line is one unit.'}</p></div>
    <nav className="sales-tabs sales-mode-tabs" aria-label="Sale entry mode">
      <button type="button" aria-pressed={mode === 'direct'} disabled={locked}
        onClick={() => setMode('direct')}>Direct Sale</button>
      <button type="button" aria-pressed={mode === 'manual'} disabled={locked}
        onClick={() => { setManualVisited(true); setMode('manual') }}>Manual Entry</button>
    </nav>
    {pendingSale.blocked && <p className="sales-warning" role="alert">Pending sale state cannot be safely read or saved. Do not submit another sale; contact the Owner for reconciliation.</p>}
    {pendingSale.pending && <div className="sales-warning" role="alert">
      <p>{sameUser ? 'A sale is unresolved in this tab. Do not start another sale.'
        : 'This tab has an unresolved sale for another account. Contact the Owner for reconciliation.'}</p>
      {sameUser && !pendingSale.pending.payload && <p>The original sale details are unavailable after reload. Contact the Owner for reconciliation; do not create a new sale.</p>}
      {sameUser && pendingSale.status === 'checking' && <p>Checking pending sale status…</p>}
      {sameUser && pendingSale.error && <p>{pendingSale.error}</p>}
      {sameUser && <div className="sales-actions">
        <button type="button" disabled={pendingSale.working || pendingSale.status === 'checking'} onClick={() => pendingSale.check()}>Check status</button>
        {pendingSale.pending.payload && <button type="button" disabled={pendingSale.working || pendingSale.status === 'checking'}
          onClick={() => pendingSale.retry(csrfToken)}>Retry exact sale</button>}
      </div>}
    </div>}
    {user.role === 'Owner' && <OwnerSaleReconciliation pendingSale={pendingSale}
      csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />}
    {mode === 'direct' && loadState === 'loading' && <p role="status">Loading sales options…</p>}
    {mode === 'direct' && loadState === 'error' && <div><p role="alert">{formError}</p>
      <button type="button" onClick={() => { setLoadState('loading'); setReload((old) => old + 1) }}>Try again</button></div>}
    {mode === 'direct' && loadState === 'ready' && <div className="sales-pos-grid">
      <section className="sales-surface sales-selection" aria-labelledby="sales-selection-title">
        <h2 id="sales-selection-title">Select Items</h2>
        <nav className="sales-tabs" aria-label="Sale item types">
          <button type="button" aria-pressed={kind === 'service'} disabled={locked || Boolean(review)}
            onClick={() => { setKind('service'); setSearch('') }}>Services</button>
          <button type="button" aria-pressed={kind === 'product'} disabled={locked || Boolean(review)}
            onClick={() => { setKind('product'); setSearch('') }}>Products</button>
        </nav>
        <label className="sales-search-label">Name
          <span className="sales-search-field">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" />
            </svg>
            <input type="search" placeholder="Search" value={search} disabled={locked || Boolean(review)}
              onChange={(event) => setSearch(event.target.value)} />
          </span>
        </label>
        <div className="sales-catalog-list">
          {visibleChoices.length === 0 ? <p className="sales-empty">{choices.length === 0
            ? `No active ${kind}s are available.` : 'No items match your search.'}</p>
            : visibleChoices.map((item) => <button className="sales-catalog-item" type="button" key={`${kind}-${item.id}`}
              disabled={locked || Boolean(review)} onClick={() => addItem(item)}
              aria-label={`Add ${item.name}, ${peso(item.current_price)}`}>
              <span>{item.name}</span><span>{peso(item.current_price)}</span>
            </button>)}
        </div>
      </section>
      <section className="sales-surface sales-current" aria-labelledby="sales-current-title">
        {review ? <div className="sales-review">
          <h2 id="sales-current-title">Review sale</h2>
          <ul>{review.lines.map((line, index) => <li key={index}><span>{line.name} — {line.staff}</span><span>{money(line.cents)}</span></li>)}</ul>
          <div className="sales-review-total"><span>Gross Total <small>(provisional)</small></span>
            <strong>{money(review.total)}</strong></div>
          <dl className="sales-review-payment">
            <div><dt>Payment Method</dt><dd>{review.payload.payment_method}</dd></div>
            {review.payload.payment_method === 'GCash' && <div><dt>GCash Reference</dt><dd>{review.payload.gcash_reference}</dd></div>}
          </dl>
          <div className="sales-actions"><button type="button" disabled={locked} onClick={() => setReview(null)}>Back</button>
            <button className="sales-primary" type="button" disabled={locked} aria-busy={pendingSale.working} onClick={confirm}>Confirm sale</button></div>
        </div> : <>
          <h2 id="sales-current-title">Current Sale</h2>
          {items.length === 0 && <p className="sales-empty">No items added yet.</p>}
          {items.map((item, index) => {
            const catalog = (item.kind === 'service' ? options.services : options.products).find((choice) => choice.id === item.itemId)
            return <div className="sales-line" key={item.line}>
              <div className="sales-line-heading"><div><strong>{index + 1}. {catalog?.name}</strong>
                <small>{item.kind === 'service' ? 'Service' : 'Product'} · one unit</small></div>
                <button type="button" disabled={locked} aria-label={`Remove ${catalog?.name} line ${index + 1}`}
                  onClick={() => setItems((old) => old.filter((row) => row.line !== item.line))}>Remove</button></div>
              <div className="sales-line-fields">
                <label>Staff<select value={item.staffId} disabled={locked} onChange={(event) => updateItem(item.line, { staffId: event.target.value })}>
                  <option value="">{item.kind === 'service' ? 'Select Staff' : 'No credited Staff'}</option>
                  {options.staff.map((staff) => <option key={staff.id} value={staff.id}>{staff.name}</option>)}
                </select></label>
                <label>Selling price<input type="text" inputMode="decimal" value={item.price}
                  disabled={locked || !(item.kind === 'service' && catalog?.allows_variable_price)}
                  onChange={(event) => updateItem(item.line, { price: event.target.value })} /></label>
              </div>
            </div>
          })}
          <div className="sales-payment">
            <label>Payment<select value={payment} disabled={locked} onChange={(event) => setPayment(event.target.value)}>
              <option value="Cash">Cash</option><option value="GCash">GCash</option></select></label>
            {payment === 'GCash' && <label>GCash reference<input type="text" value={reference} disabled={locked}
              onChange={(event) => setReference(event.target.value)} /></label>}
          </div>
          <div className="sales-total" aria-live="polite"><span>Provisional gross total</span>
            {provisional === null ? <span>Enter valid selling prices</span> : <strong>{money(provisional)}</strong>}
          </div>
          {formError && <p className="sales-error" role="alert">{formError}</p>}
          <button className="sales-primary sales-review-button" type="button" disabled={locked} onClick={prepareReview}>Review sale</button>
        </>}
      </section>
    </div>}
    </>}
    {manualVisited && <div hidden={mode !== 'manual' || confirmed}>
      <ManualEntryForm user={user} disabled={locked} resetToken={manualReset} onDraftChange={setManualDraft}
        onSubmit={confirmManual} onRevalidateSession={onRevalidateSession} />
    </div>}
  </section>
}
