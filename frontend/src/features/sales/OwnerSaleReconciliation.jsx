import { useRef, useState } from 'react'

import { acknowledgeOwnerSale, getOwnerSaleStatus } from './salesApi.js'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

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
  </section>
}
