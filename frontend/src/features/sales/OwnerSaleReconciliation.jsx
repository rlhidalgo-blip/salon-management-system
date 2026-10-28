import { useRef, useState } from 'react'

import { acknowledgeOwnerSale, cancelSaleAttempt, findSaleAttempts, getOwnerSaleStatus,
  getSaleAttempt } from './salesApi.js'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const referencePattern = /^(?:DS-\d{12,}|PAPER-\d{8}-\d{3})$/

function OwnerAttempts({ csrfToken, onRevalidateSession, onCommittedSelected }) {
  const [recordingUserId, setRecordingUserId] = useState('')
  const [reference, setReference] = useState('')
  const [rows, setRows] = useState([])
  const [searched, setSearched] = useState(false)
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [target, setTarget] = useState(null)
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const generation = useRef(0)
  const loadingRef = useRef(false)
  const cancellingRef = useRef(false)
  const dialogRef = useRef(null)
  const cancelButton = useRef(null)
  const returnFocus = useRef(null)
  const queryRef = useRef(null)

  function closeDialog() {
    if (dialogRef.current?.open) dialogRef.current.close()
    setTarget(null)
    setReason('')
    setEvidence(false)
    returnFocus.current?.focus()
  }

  function invalidate(setter, value) {
    if (cancellingRef.current) return
    generation.current += 1
    loadingRef.current = false
    setLoading(false)
    queryRef.current = null
    setter(value)
    setRows([])
    setSearched(false)
    setMore(false)
    setMessage('')
    if (!cancellingRef.current) closeDialog()
  }

  async function handleFailure(error, fallback) {
    if (error.status === 401) {
      try { await onRevalidateSession() } catch { /* Keep the result unverified. */ }
    }
    setMessage(error.status === 403 ? 'Owner access is required.'
      : error.status === 404 ? 'Attempt was not found or is no longer available.'
        : error.status === 422 ? 'Check the recording user ID, reference, or cancellation reason.'
          : error.status === 409 ? 'Attempt changed. Recheck its status; no browser pending state was cleared.'
            : fallback)
  }

  async function search(next = false) {
    if (loadingRef.current || cancellingRef.current) return
    const id = Number(recordingUserId)
    const normalized = reference.trim().toUpperCase()
    if (!Number.isSafeInteger(id) || id <= 0 || (normalized && !referencePattern.test(normalized))) {
      setMessage('Enter a valid recording user ID and exact DS or PAPER reference.')
      return
    }
    const query = next ? queryRef.current : { id, reference: normalized }
    if (!query || (next && (!more || rows.length === 0))) return
    const cursor = next ? rows.at(-1).id : undefined
    const requestId = ++generation.current
    loadingRef.current = true
    setLoading(true)
    setMessage('')
    if (!next) {
      setRows([])
      setSearched(false)
      setMore(false)
      queryRef.current = query
    }
    try {
      const result = await findSaleAttempts(query.id, query.reference, cursor)
      if (requestId !== generation.current) return
      if (!Array.isArray(result) || result.some((row) => row.user_id !== query.id ||
          !['Reserved', 'Committed', 'Cancelled'].includes(row.state) || !Number.isSafeInteger(row.id))) throw new Error()
      setRows(next ? (previous) => [...previous, ...result] : result)
      setMore(result.length === 50)
      setSearched(true)
    } catch (error) {
      if (requestId !== generation.current) return
      if (!next) queryRef.current = null
      await handleFailure(error, 'Could not investigate attempts. Try again.')
    } finally {
      if (requestId === generation.current) {
        loadingRef.current = false
        setLoading(false)
      }
    }
  }

  async function openCancel(row, event) {
    if (loadingRef.current || cancellingRef.current || row.state !== 'Reserved') return
    returnFocus.current = event.currentTarget
    const requestId = ++generation.current
    setLoading(true)
    setMessage('')
    try {
      const fresh = await getSaleAttempt(row.id)
      if (requestId !== generation.current) return
      if (fresh.id !== row.id || fresh.user_id !== row.user_id ||
          fresh.idempotency_key !== row.idempotency_key || fresh.state !== 'Reserved') {
        setMessage('Attempt changed. Search again before cancellation.')
        return
      }
      setTarget(fresh)
      setReason('')
      setEvidence(false)
      dialogRef.current.showModal()
      cancelButton.current?.focus()
    } catch (error) {
      if (requestId === generation.current) await handleFailure(error, 'Could not verify attempt. Search again.')
    } finally {
      if (requestId === generation.current) setLoading(false)
    }
  }

  async function refreshDetail(id, requestId) {
    try {
      const fresh = await getSaleAttempt(id)
      if (requestId === generation.current) {
        setRows((previous) => previous.map((row) => row.id === id ? fresh : row))
        setMessage(`Attempt #${id} is now ${fresh.state}. Browser pending state was not cleared.`)
      }
    } catch (error) {
      if (requestId === generation.current) await handleFailure(error,
        'Cancellation outcome is uncertain. Recheck this attempt; do not clear browser pending state.')
    }
  }

  async function confirmCancel() {
    const normalizedReason = reason.trim()
    if (cancellingRef.current || !target || !dialogRef.current?.open || !evidence ||
        !normalizedReason || normalizedReason.length > 500) return
    const selected = target
    const requestId = ++generation.current
    cancellingRef.current = true
    setCancelling(true)
    setMessage('')
    try {
      const fresh = await getSaleAttempt(selected.id)
      if (requestId !== generation.current || fresh.id !== selected.id || fresh.user_id !== selected.user_id ||
          fresh.idempotency_key !== selected.idempotency_key || fresh.state !== 'Reserved') {
        closeDialog()
        setMessage('Attempt changed. Recheck its status; no cancellation was sent.')
        await refreshDetail(selected.id, requestId)
        return
      }
      const result = await cancelSaleAttempt(selected.id, normalizedReason, csrfToken)
      if (requestId !== generation.current) return
      closeDialog()
      if (result.id !== selected.id || result.state !== 'Cancelled' ||
          result.idempotency_key !== selected.idempotency_key) throw new Error()
      setRows((previous) => previous.map((row) => row.id === selected.id ? result : row))
      setMessage(`Attempt #${selected.id} cancelled. Its key and reference remain fenced. Browser pending state was not cleared.`)
    } catch (error) {
      if (requestId !== generation.current) return
      closeDialog()
      await handleFailure(error, 'Cancellation outcome is uncertain. Rechecking attempt status.')
      if (!error.status || error.status === 409 || error.status >= 500) {
        await refreshDetail(selected.id, requestId)
      }
    } finally {
      cancellingRef.current = false
      if (requestId === generation.current) setCancelling(false)
    }
  }

  return <div className="sales-attempts" aria-labelledby="sales-attempts-title">
    <h3 id="sales-attempts-title">Sale Attempts</h3>
    <div className="sales-reconcile-fields">
      <label>Attempt recording user ID<input type="number" min="1" step="1" value={recordingUserId}
        onChange={(event) => invalidate(setRecordingUserId, event.target.value)} /></label>
      <label>Exact Direct or paper reference (optional)<input type="text" value={reference} autoComplete="off"
        onChange={(event) => invalidate(setReference, event.target.value)} /></label>
    </div>
    <div className="sales-actions"><button type="button" disabled={loading || cancelling} onClick={() => search()}>Search attempts</button></div>
    {loading && <p role="status">Checking attempts…</p>}
    {searched && rows.length === 0 && <p>No attempts found for this search.</p>}
    {rows.length > 0 && <ul className="sales-attempt-list">{rows.map((row) => <li key={row.id}>
      <div><strong>Attempt #{row.id}</strong> <span>{row.state}</span></div>
      <p>User #{row.user_id} · {row.source} · {row.direct_reference || row.manual_reference || 'No reference'}</p>
      <p>Created {new Date(row.created_at).toLocaleString('en-PH', { timeZone: 'Asia/Manila' })}</p>
      {row.state === 'Reserved' && <button type="button" disabled={loading || cancelling}
        onClick={(event) => openCancel(row, event)}>Cancel attempt #{row.id}</button>}
      {row.state === 'Committed' && <button type="button" disabled={loading || cancelling}
        onClick={() => onCommittedSelected(row.user_id, row.idempotency_key)}>Use exact-key lookup for attempt #{row.id}</button>}
      {row.state === 'Cancelled' && <p>Key and reference are permanently fenced. No reactivation or electronic replacement is available.</p>}
    </li>)}</ul>}
    {more && <div className="sales-actions"><button type="button" disabled={loading || cancelling}
      onClick={() => search(true)}>Load more attempts</button></div>}
    <dialog ref={dialogRef} className="sales-leave-dialog" aria-labelledby="attempt-cancel-title"
      aria-describedby="attempt-cancel-description"
      onCancel={(event) => { event.preventDefault(); if (!cancellingRef.current) closeDialog() }}>
      <h2 id="attempt-cancel-title">Cancel reserved attempt #{target?.id}</h2>
      <p id="attempt-cancel-description">Reference: {target?.direct_reference || target?.manual_reference}. Verify external evidence first. Cancellation permanently fences this key and reference; it does not clear any browser pending state or create a replacement sale.</p>
      <label>Cancellation reason<textarea value={reason} maxLength={500} disabled={cancelling}
        onChange={(event) => setReason(event.target.value)} /></label>
      <label className="sales-manual-attestation"><input type="checkbox" checked={evidence} disabled={cancelling}
        onChange={(event) => setEvidence(event.target.checked)} />I verified the external receipt/payment evidence for this attempt.</label>
      <div className="sales-leave-actions">
        <button type="button" ref={cancelButton} disabled={cancelling} onClick={closeDialog}>Keep attempt</button>
        <button type="button" disabled={cancelling || !evidence || !reason.trim() || reason.trim().length > 500}
          onClick={confirmCancel}>Confirm cancellation</button>
      </div>
    </dialog>
    {message && <p role="alert">{message}</p>}
  </div>
}

export default function OwnerSaleReconciliation({ pendingSale, csrfToken, onRevalidateSession }) {
  const [userId, setUserId] = useState(String(pendingSale.pending?.userId ?? ''))
  const [key, setKey] = useState(pendingSale.pending?.key ?? '')
  const [found, setFound] = useState(null)
  const [checked, setChecked] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [confirmation, setConfirmation] = useState(null)
  const sequence = useRef(0)
  const dialog = useRef(null)
  const cancelButton = useRef(null)
  const acknowledgeButton = useRef(null)
  const submitting = useRef(false)

  function closeConfirmation() {
    if (dialog.current?.open) dialog.current.close()
    setConfirmation(null)
    acknowledgeButton.current?.focus()
  }

  function openConfirmation() {
    if (busy || acknowledged || found?.status !== 'committed' || !found.sale || !checked ||
        Number(userId) !== checked.userId || key.trim().toLowerCase() !== checked.key) return
    setConfirmation({ ...checked, saleId: found.sale.id })
    dialog.current.showModal()
    cancelButton.current?.focus()
  }

  function change(setter, value) {
    closeConfirmation()
    sequence.current += 1
    setBusy(false)
    setter(value)
    setFound(null)
    setChecked(null)
    setAcknowledged(false)
    setMessage('')
  }

  function selectCommitted(targetUserId, targetKey) {
    change(setUserId, String(targetUserId))
    setKey(targetKey)
    setMessage('Use Check sale for a fresh committed lookup before acknowledgment.')
  }

  async function investigate() {
    if (busy) return
    closeConfirmation()
    const targetId = Number(userId)
    const targetKey = key.trim().toLowerCase()
    if (!Number.isSafeInteger(targetId) || targetId <= 0 || !uuid.test(targetKey)) {
      setMessage('Enter a valid recording user ID and exact sale UUID.')
      return
    }
    const requestId = ++sequence.current
    setBusy(true)
    setFound(null)
    setChecked(null)
    setAcknowledged(false)
    setMessage('')
    try {
      const result = await getOwnerSaleStatus(targetId, targetKey)
      if (requestId !== sequence.current) return
      setChecked({ userId: targetId, key: targetKey })
      setFound(result)
    } catch (error) {
      if (requestId !== sequence.current) return
      if (error.status === 401) {
        try { await onRevalidateSession() } catch { /* Keep the request retryable. */ }
      }
      setMessage(error.status === 403 ? 'Owner access is required.'
        : error.status === 404 ? 'Recording user was not found.'
          : error.status === 422 ? 'Check the user ID and UUID.'
            : 'Could not check the sale now. Try again.')
    } finally {
      if (requestId === sequence.current) setBusy(false)
    }
  }

  async function acknowledge() {
    if (submitting.current || busy) return
    if (acknowledged || !dialog.current?.open || !confirmation ||
        found?.status !== 'committed' || !found.sale || found.sale.id !== confirmation.saleId ||
        !checked || checked.userId !== confirmation.userId || checked.key !== confirmation.key ||
        Number(userId) !== confirmation.userId || key.trim().toLowerCase() !== confirmation.key) {
      closeConfirmation()
      return
    }
    submitting.current = true
    const requestId = ++sequence.current
    setBusy(true)
    setMessage('')
    try {
      const result = await acknowledgeOwnerSale(checked.userId, checked.key, csrfToken)
      if (requestId !== sequence.current) return
      if (result.status !== 'committed' || result.recording_user_id !== checked.userId ||
          result.idempotency_key !== checked.key || result.sale?.id !== found.sale.id) throw new Error()
      setAcknowledged(true)
      const clearance = pendingSale.clearAcknowledged(result)
      closeConfirmation()
      setMessage(clearance === 'cleared' ? 'Committed sale acknowledged. Matching pending identifier cleared in this tab.'
        : clearance === 'no_match' ? 'Committed sale acknowledged. No matching pending identifier in this tab was cleared.'
          : 'Committed sale acknowledged, but browser pending state remains blocked. Contact the Owner before another sale.')
    } catch (error) {
      if (requestId !== sequence.current) return
      closeConfirmation()
      setFound(null)
      setChecked(null)
      if (error.status === 401) {
        try { await onRevalidateSession() } catch { /* Keep the result unresolved. */ }
      }
      setMessage(error.status === 403 ? 'Owner acknowledgment was denied.'
        : error.status === 404 ? 'Recording user was not found.'
          : error.status === 409 ? 'Sale is not confirmed committed. Recheck its status; do not clear pending state.'
            : error.status === 422 ? 'Check the user ID and UUID.'
              : 'Acknowledgment could not be confirmed. Pending state was not cleared; recheck before retrying.')
    } finally {
      submitting.current = false
      if (requestId === sequence.current) setBusy(false)
    }
  }

  return <section className="sales-surface sales-reconciliation" aria-labelledby="sales-reconciliation-title">
    <h2 id="sales-reconciliation-title">Owner Sale Reconciliation</h2>
    <div className="sales-reconcile-fields">
      <label>Recording user ID<input type="number" min="1" step="1" value={userId}
        onChange={(event) => change(setUserId, event.target.value)} /></label>
      <label>Exact sale UUID<input type="text" value={key} autoComplete="off"
        onChange={(event) => change(setKey, event.target.value)} /></label>
    </div>
    <div className="sales-actions"><button type="button" disabled={busy} onClick={investigate}>Check sale</button></div>
    {found?.status === 'processing' && <p role="status">Sale key is processing. Check again later; do not clear pending state.</p>}
    {found?.status === 'not_committed_at_check' && <p role="status">No committed sale at this check. A delayed request may still commit; do not clear pending state.</p>}
    {found?.status === 'committed' && found.sale && <div>
      <p role="status">Transaction #{found.sale.id} — {found.sale.status}. Recorded by user #{found.sale.recorded_by_user_id}.</p>
      <div className="sales-actions"><button type="button" disabled={busy || acknowledged}
        ref={acknowledgeButton} onClick={openConfirmation}>Acknowledge committed sale</button></div>
    </div>}
    <dialog ref={dialog} className="sales-leave-dialog" aria-labelledby="reconcile-confirm-title" aria-describedby="reconcile-confirm-description"
      onCancel={(event) => { event.preventDefault(); if (!submitting.current) closeConfirmation() }}>
      <h2 id="reconcile-confirm-title">Acknowledge transaction #{confirmation?.saleId}</h2>
      <p id="reconcile-confirm-description">Confirm this committed sale was reviewed. Only a matching pending identifier in this browser tab will be cleared. The sale itself will not change.</p>
      <div className="sales-leave-actions">
        <button type="button" ref={cancelButton} disabled={busy} onClick={closeConfirmation}>Cancel</button>
        <button type="button" disabled={busy} onClick={acknowledge}>Confirm acknowledgment</button>
      </div>
    </dialog>
    {message && <p role="alert">{message}</p>}
    {pendingSale.protocol === 'reserved_v1' && <OwnerAttempts csrfToken={csrfToken}
      onRevalidateSession={onRevalidateSession} onCommittedSelected={selectCommitted} />}
  </section>
}
