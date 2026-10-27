import { useEffect, useRef, useState } from 'react'

import { getTransactionDetail, getTransactionHistory, voidTransaction } from './transactionHistoryApi.js'
import './TransactionHistory.css'

const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' })
const manilaTime = new Intl.DateTimeFormat('en-PH', {
  timeZone: 'Asia/Manila', year: 'numeric', month: 'short', day: 'numeric',
  hour: 'numeric', minute: '2-digit',
})
const manilaDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit',
})

function money(value) {
  // Display only: all amounts and financial snapshots come from PostgreSQL.
  return peso.format(Number(value))
}

function time(value) {
  return manilaTime.format(new Date(value))
}

function todayInManila() {
  return manilaDay.format(new Date())
}

function messageFor(error, action) {
  if (error.status === 403) return 'You do not have permission to view or change this transaction.'
  if (error.status === 404) return 'Transaction not found or no longer available to you.'
  if (error.status === 409) return 'This transaction is already voided. Its status will be checked again.'
  if (error.status === 422) return action === 'void'
    ? 'Enter a nonblank reason of at most 500 characters.' : 'Invalid date, page, or transaction request.'
  return 'Transaction History is temporarily unavailable. Please try again.'
}

function Status({ value }) {
  return <span className={`history-status history-status-${value.toLowerCase()}`}>{value}</span>
}

function Summary({ data }) {
  return <dl className="history-summary">
    <div><dt>Gross Sales</dt><dd>{money(data.gross_sales)}</dd></div>
    <div><dt>Staff Commission</dt><dd>{money(data.total_staff_commission)}</dd></div>
    <div><dt>Business Share</dt><dd>{money(data.total_business_share)}</dd></div>
  </dl>
}

function Item({ item }) {
  return <li className="history-item">
    <div className="history-item-heading">
      <strong>{item.item_name_snapshot}</strong><strong>{money(item.selling_price)}</strong>
    </div>
    <p>{item.staff_id == null ? 'No credited Staff' : item.staff_name
      ? `Credited Staff: ${item.staff_name} (current name)`
      : `Credited Staff: Staff #${item.staff_id}`}</p>
    <dl className="history-item-finances">
      <div><dt>Commission rule snapshot</dt><dd>{item.commission_type_snapshot == null
        ? 'None' : `${item.commission_type_snapshot} · ${item.commission_type_snapshot === 'Percentage'
          ? `${item.commission_value_snapshot}%` : money(item.commission_value_snapshot)}`}</dd></div>
      <div><dt>Staff Commission</dt><dd>{money(item.staff_commission)}</dd></div>
      <div><dt>Business Share</dt><dd>{money(item.business_share)}</dd></div>
    </dl>
  </li>
}

export default function TransactionHistory({ user, csrfToken, onRevalidateSession }) {
  const owner = user.role === 'Owner'
  const [page, setPage] = useState({ businessDate: '', cursors: [null], index: 0 })
  const [listReload, setListReload] = useState(0)
  const [listing, setListing] = useState({ state: 'loading', key: '', items: [], nextCursor: null, error: '' })
  const [selectedId, setSelectedId] = useState(null)
  const [detailReload, setDetailReload] = useState(0)
  const [detail, setDetail] = useState({ state: 'idle', id: null, record: null, error: '' })
  const [notice, setNotice] = useState('')
  const [voidOpen, setVoidOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState('')
  const [voidBusy, setVoidBusy] = useState(false)
  const [voidUncertain, setVoidUncertain] = useState(false)
  const voidPending = useRef(false)
  const voidDialog = useRef(null)
  const voidButton = useRef(null)
  const cursor = page.cursors[page.index]
  const queryKey = `${page.businessDate}|${cursor || ''}|${listReload}`
  const currentList = listing.key === queryKey ? listing : { state: 'loading', items: [] }
  const currentDetail = detail.id === selectedId ? detail : { state: 'loading', record: null }

  useEffect(() => {
    const controller = new AbortController()
    setListing({ state: 'loading', key: queryKey, items: [], nextCursor: null, error: '' })
    getTransactionHistory({ businessDate: page.businessDate, cursor, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return
        setListing({ state: 'ready', key: queryKey, items: result.items,
          nextCursor: result.next_cursor, error: '' })
      }).catch(async (error) => {
        if (controller.signal.aborted) return
        if (error.status === 422 && cursor) {
          // A cursor from the older descending API must not strand an open tab.
          setNotice('History pagination changed. Showing the first page again.')
          setPage((previous) => previous.businessDate === page.businessDate &&
            previous.cursors[previous.index] === cursor
            ? { businessDate: previous.businessDate, cursors: [null], index: 0 } : previous)
          return
        }
        if (error.status === 401) {
          try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
        }
        if (!controller.signal.aborted) setListing({ state: 'error', key: queryKey, items: [],
          nextCursor: null, error: messageFor(error, 'list') })
      })
    return () => controller.abort()
  }, [page.businessDate, cursor, listReload, queryKey, onRevalidateSession])

  useEffect(() => {
    if (selectedId == null) return
    const controller = new AbortController()
    setDetail({ state: 'loading', id: selectedId, record: null, error: '' })
    getTransactionDetail(selectedId, controller.signal).then((record) => {
      if (!controller.signal.aborted) setDetail({ state: 'ready', id: selectedId, record, error: '' })
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) setDetail({ state: 'error', id: selectedId,
        record: null, error: messageFor(error, 'detail') })
    })
    return () => controller.abort()
  }, [selectedId, detailReload, onRevalidateSession])

  useEffect(() => {
    if (owner) return
    let observedDay = todayInManila()
    const checkDay = () => {
      const day = todayInManila()
      if (day === observedDay) return
      observedDay = day
      setSelectedId(null)
      setNotice('The Manila business date changed. Showing today’s transactions.')
      setPage({ businessDate: '', cursors: [null], index: 0 })
      setListReload((count) => count + 1)
    }
    const interval = setInterval(checkDay, 30_000)
    window.addEventListener('focus', checkDay)
    document.addEventListener('visibilitychange', checkDay)
    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', checkDay)
      document.removeEventListener('visibilitychange', checkDay)
    }
  }, [owner])

  useEffect(() => {
    if (voidOpen && !voidDialog.current?.open) voidDialog.current?.showModal()
    if (!voidOpen && voidDialog.current?.open) voidDialog.current.close()
  }, [voidOpen])

  function changeDate(event) {
    setSelectedId(null)
    setNotice('')
    setPage({ businessDate: event.target.value, cursors: [null], index: 0 })
  }

  function view(id) {
    setVoidUncertain(false)
    setNotice('')
    setSelectedId(id)
  }

  function backToList() {
    setSelectedId(null)
    setVoidOpen(false)
    setVoidUncertain(false)
    setNotice('')
    setListReload((count) => count + 1)
  }

  function nextPage() {
    if (currentList.state !== 'ready' || !currentList.nextCursor) return
    setPage((previous) => ({ ...previous, index: previous.index + 1,
      cursors: [...previous.cursors.slice(0, previous.index + 1), currentList.nextCursor] }))
  }

  function startVoid() {
    setReason('')
    setReasonError('')
    setVoidOpen(true)
  }

  function closeVoid() {
    if (voidPending.current) return
    setVoidOpen(false)
    voidButton.current?.focus()
  }

  async function confirmVoid(event) {
    event.preventDefault()
    if (voidPending.current || !owner || currentDetail.state !== 'ready' ||
        currentDetail.record.status !== 'Completed') return
    const trimmed = reason.trim()
    if (!trimmed || trimmed.length > 500) {
      setReasonError('Enter a nonblank reason of at most 500 characters.')
      return
    }
    voidPending.current = true
    setVoidBusy(true)
    setReasonError('')
    try {
      const updated = await voidTransaction(selectedId, trimmed, csrfToken)
      setDetail({ state: 'ready', id: selectedId, record: updated, error: '' })
      setVoidOpen(false)
      setNotice('Transaction voided. Historical items and financial snapshots were preserved.')
      setListReload((count) => count + 1)
    } catch (error) {
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Do not claim logout. */ }
      }
      if (error.status === 409 || error.status === 0 || error.status >= 500) {
        setVoidUncertain(true)
        setVoidOpen(false)
        setNotice(error.status === 409 ? messageFor(error, 'void')
          : 'Void outcome could not be confirmed. Check the refreshed status before any further action.')
        setDetailReload((count) => count + 1)
        setListReload((count) => count + 1)
      } else if (error.status === 422) {
        setReasonError(messageFor(error, 'void'))
      } else {
        setVoidOpen(false)
        setNotice(messageFor(error, 'void'))
        if (error.status === 404) setDetailReload((count) => count + 1)
      }
    } finally {
      voidPending.current = false
      setVoidBusy(false)
    }
  }

  return <section className="transaction-history" aria-labelledby="history-title">
    <header className="history-heading">
      <h1 id="history-title">Transaction History</h1>
      <p>{owner ? 'Review current and historical sales.' : 'Today’s Manila-date sales.'}</p>
    </header>
    {selectedId == null ? <>
      {owner && <div className="history-date-filter">
        <label htmlFor="history-date">Business date</label>
        <input id="history-date" type="date" value={page.businessDate} onChange={changeDate} />
        <span>Leave blank for the current Manila business date.</span>
      </div>}
      {notice && <p className="history-notice" role="status">{notice}</p>}
      {currentList.state === 'loading' && <p role="status">Loading transactions…</p>}
      {currentList.state === 'error' && <div role="alert"><p>{currentList.error}</p>
        <button type="button" onClick={() => setListReload((count) => count + 1)}>Try again</button></div>}
      {currentList.state === 'ready' && <>
        <div className="history-results">
          {currentList.items.length === 0 ? <p className="history-empty">No transactions for this business date.</p>
            : <table className="history-table">
              <thead><tr><th scope="col">Transaction</th><th scope="col">Manila time</th>
                <th scope="col">Status</th><th scope="col">Payment</th><th scope="col">Gross Sales</th>
                <th scope="col">Staff Commission</th><th scope="col">Business Share</th><th scope="col">Action</th></tr></thead>
              <tbody>{currentList.items.map((row) => <tr key={row.id}>
                <td data-label="Transaction">#{row.id}</td>
                <td data-label="Manila time">{time(row.date_time)}</td>
                <td data-label="Status"><Status value={row.status} /></td>
                <td data-label="Payment">{row.payment_method}</td>
                <td data-label="Gross Sales" className="history-money">{money(row.gross_sales)}</td>
                <td data-label="Staff Commission" className="history-money">{money(row.total_staff_commission)}</td>
                <td data-label="Business Share" className="history-money">{money(row.total_business_share)}</td>
                <td data-label="Action"><button type="button" onClick={() => view(row.id)}
                  aria-label={`View transaction #${row.id}`}>View</button></td>
              </tr>)}</tbody>
            </table>}
        </div>
        <nav className="history-pagination" aria-label="Transaction pages">
          <button type="button" onClick={() => setPage((previous) => ({ ...previous, index: previous.index - 1 }))}
            disabled={page.index === 0}>Back</button>
          <span>Page {page.index + 1}</span>
          <button type="button" onClick={nextPage} disabled={!currentList.nextCursor}>Next</button>
        </nav>
      </>}
    </> : <>
      <button className="history-back" type="button" onClick={backToList}
        disabled={voidBusy}>Back to history</button>
      {notice && <p className="history-notice" role="status">{notice}</p>}
      {currentDetail.state === 'loading' && <p role="status">Loading transaction details…</p>}
      {currentDetail.state === 'error' && <div role="alert"><p>{currentDetail.error}</p>
        <button type="button" onClick={() => setDetailReload((count) => count + 1)}>Try again</button></div>}
      {currentDetail.state === 'ready' && <article className="history-detail">
        <div className="history-detail-heading"><div>
          <h2>Transaction #{currentDetail.record.id}</h2>
          <p>{time(currentDetail.record.date_time)} · Business date {currentDetail.record.business_date}</p>
        </div><Status value={currentDetail.record.status} /></div>
        <ul className="history-items">{currentDetail.record.items.map((item) => <Item key={item.id} item={item} />)}</ul>
        <Summary data={currentDetail.record} />
        <dl className="history-metadata">
          <div><dt>Payment method</dt><dd>{currentDetail.record.payment_method}</dd></div>
          {currentDetail.record.payment_method === 'GCash' &&
            <div><dt>GCash reference</dt><dd>{currentDetail.record.gcash_reference}</dd></div>}
          {owner && <>
            <div><dt>Entry source</dt><dd>{currentDetail.record.entry_source}</dd></div>
            {currentDetail.record.entry_source === 'Manual' && <>
              <div><dt>Paper reference</dt><dd>{currentDetail.record.manual_reference}</dd></div>
              <div><dt>Entry time</dt><dd>{time(currentDetail.record.created_at)}</dd></div>
            </>}
          </>}
          {owner && currentDetail.record.status === 'Voided' && <>
            <div><dt>Void reason</dt><dd>{currentDetail.record.void_reason}</dd></div>
            <div><dt>Voided by</dt><dd>User #{currentDetail.record.voided_by_user_id}</dd></div>
            <div><dt>Voided at</dt><dd>{currentDetail.record.voided_at && time(currentDetail.record.voided_at)}</dd></div>
          </>}
        </dl>
        {owner && currentDetail.record.status === 'Completed' && !voidUncertain &&
          <button ref={voidButton} type="button" onClick={startVoid}>Void transaction</button>}
        {voidUncertain && <button type="button" onClick={() => setDetailReload((count) => count + 1)}>
          Check status again</button>}
      </article>}
    </>}
    {owner && <dialog ref={voidDialog} onCancel={(event) => { if (voidBusy) event.preventDefault() }}
      onClose={() => { if (!voidBusy) setVoidOpen(false) }} aria-labelledby="history-void-title">
      <form onSubmit={confirmVoid} noValidate>
        <h2 id="history-void-title">Void transaction #{selectedId}?</h2>
        <p>This keeps the sale and its historical financial snapshots. Confirm only if this transaction should be voided.</p>
        <label htmlFor="history-void-reason">Reason</label>
        <textarea id="history-void-reason" value={reason} maxLength={500} required
          onChange={(event) => setReason(event.target.value)} aria-invalid={!!reasonError}
          aria-describedby={reasonError ? 'history-void-error' : undefined} />
        {reasonError && <p id="history-void-error" role="alert">{reasonError}</p>}
        <div className="history-dialog-actions">
          <button type="button" onClick={closeVoid} disabled={voidBusy}>Cancel</button>
          <button className="history-danger" type="submit" disabled={voidBusy}
            aria-busy={voidBusy}>{voidBusy ? 'Voiding…' : 'Confirm void'}</button>
        </div>
      </form>
    </dialog>}
  </section>
}
