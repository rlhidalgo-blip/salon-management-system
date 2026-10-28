import { useCallback, useEffect, useRef, useState } from 'react'

import { createManualSale, createSale, getOpenSaleAttempt, getOwnSaleAttemptByKey, getSaleStatus,
  getSalesCapabilities, reserveSaleAttempt } from './salesApi.js'

const STORAGE_KEY = 'yabs-pending-sale'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function storedPending() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw === null) return { pending: null, blocked: false }
    const value = JSON.parse(raw)
    if (!value || !UUID.test(value.key) || !Number.isSafeInteger(value.userId) || value.userId <= 0 ||
        Object.keys(value).sort().join(',') !== 'key,userId') {
      return { pending: null, blocked: true }
    }
    return { pending: { ...value, payload: null }, blocked: false }
  } catch {
    return { pending: null, blocked: true }
  }
}

function frozenPayload(payload) {
  const copy = JSON.parse(JSON.stringify(payload))
  const freeze = (value) => {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze)
      Object.freeze(value)
    }
  }
  freeze(copy)
  return copy
}

function validOpenAttempt(value, userId) {
  return value === null || (value && value.state === 'Reserved' && value.user_id === userId &&
    Number.isSafeInteger(value.id) && value.id > 0 && UUID.test(value.idempotency_key) &&
    (value.source === 'Direct' || value.source === 'Manual'))
}

function validReservation(value, attempt) {
  return value && value.state === 'Reserved' && value.user_id === attempt.userId &&
    value.idempotency_key?.toLowerCase() === attempt.key.toLowerCase() &&
    value.source === (attempt.mode === 'manual' ? 'Manual' : 'Direct') &&
    Number.isSafeInteger(value.id) && value.id > 0 &&
    (attempt.mode === 'manual'
      ? value.manual_reference === attempt.payload.manual_reference
      : /^DS-\d{12,}$/.test(value.direct_reference) && value.manual_reference === null)
}

export function usePendingSale(user, onRevalidateSession) {
  // AuthenticatedHome mounts only after /me succeeds. This runs no earlier.
  const initial = useRef(null)
  if (initial.current === null) initial.current = storedPending()
  const [pending, setPending] = useState(initial.current.pending)
  const [blocked, setBlocked] = useState(initial.current.blocked)
  const [status, setStatus] = useState(pending ? 'checking' : 'idle')
  const [sale, setSale] = useState(null)
  const [error, setError] = useState('')
  const busy = useRef(false)
  const [working, setWorking] = useState(false)
  const current = useRef(pending)
  const [protocol, setProtocol] = useState('loading')
  const [openAttempt, setOpenAttempt] = useState(null)
  const [cancelledCheck, setCancelledCheck] = useState(null)
  const userRef = useRef(user.id)
  const protocolRef = useRef(protocol)
  const mounted = useRef(true)
  userRef.current = user.id
  protocolRef.current = protocol

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  function matchesPending(attempt) {
    if (!attempt || current.current !== attempt || userRef.current !== attempt.userId) return false
    const stored = storedPending()
    return !stored.blocked && stored.pending?.key === attempt.key &&
      stored.pending.userId === attempt.userId
  }

  const negotiate = useCallback(async () => {
    setCancelledCheck(null)
    setProtocol('loading')
    try {
      const selected = await getSalesCapabilities()
      if (selected === 'legacy' && openAttempt) throw new Error('Open reservation cannot use legacy protocol')
      const open = selected === 'reserved_v1' ? await getOpenSaleAttempt() : null
      if (!validOpenAttempt(open, user.id)) throw new Error('Invalid open reservation')
      setOpenAttempt(open)
      setProtocol(selected)
    } catch (failure) {
      if (failure.status === 401) {
        try { await onRevalidateSession() } catch { /* Keep sales disabled. */ }
      }
      setProtocol('error')
      setError('Sales protocol could not be verified. Electronic sales are blocked; try again or contact the Owner.')
    }
  }, [onRevalidateSession, openAttempt, user.id])

  const check = useCallback(async (key = current.current?.key) => {
    if (!key || blocked || current.current?.userId !== user.id) return
    setCancelledCheck(null)
    setStatus('checking')
    setError('')
    try {
      const result = await getSaleStatus(key)
      if (current.current?.key !== key) return
      if (result.status === 'committed' && result.sale) {
        setSale(result.sale)
        try {
          const saved = storedPending()
          if (saved.blocked || saved.pending?.key !== key || saved.pending.userId !== user.id) throw new Error()
          sessionStorage.removeItem(STORAGE_KEY)
          current.current = null
          setPending(null)
          setOpenAttempt((open) => open?.idempotency_key === key ? null : open)
          setStatus('committed')
        } catch {
          setBlocked(true)
          setStatus('unresolved')
          setError('Sale confirmed, but pending browser state could not be cleared. Contact the Owner before another sale.')
        }
      } else if (result.status === 'processing' || result.status === 'not_committed_at_check') {
        setStatus('unresolved')
        setError(result.status === 'processing' ? 'Sale is still processing. Check status again.'
          : 'No committed sale found at this check. The earlier request may still complete. Do not start another sale.')
      } else {
        throw new Error('Unexpected sale status')
      }
    } catch (failure) {
      if (failure.status === 401) {
        try { await onRevalidateSession() } catch { /* Keep pending state. */ }
      }
      setStatus('unresolved')
      setError(failure.status === 403 ? 'You do not have permission to check this sale. Contact the Owner.'
        : 'Unable to confirm this sale now. Check status again or contact the Owner.')
    }
  }, [blocked, onRevalidateSession, user.id])

  useEffect(() => {
    if (pending?.userId === user.id && !blocked && status === 'checking') void check(pending.key)
    // Initial session-restoration check only; explicit rechecks use check().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function submit(payload, csrfToken, mode = 'direct') {
    if (busy.current || blocked || current.current || openAttempt ||
        (protocol !== 'legacy' && protocol !== 'reserved_v1')) return false
    if (mode !== 'direct' && mode !== 'manual') return false
    busy.current = true
    setWorking(true)
    setError('')
    setSale(null)
    try {
      const fresh = await getSalesCapabilities()
      if (fresh !== protocol) throw new Error('Sales protocol changed')
      if (fresh === 'reserved_v1') {
        const open = await getOpenSaleAttempt()
        if (!validOpenAttempt(open, user.id)) throw new Error('Invalid open reservation')
        if (open) {
          setOpenAttempt(open)
          setError('An open reservation already exists. Contact the Owner before another electronic sale.')
          return false
        }
      }
      const existing = storedPending()
      if (existing.blocked || existing.pending) {
        setBlocked(true)
        setError('Another pending identifier exists in this tab. Do not overwrite it; contact the Owner.')
        return false
      }
      const exactPayload = frozenPayload(payload)
      const saved = { key: crypto.randomUUID(), userId: user.id }
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved))
        if (sessionStorage.getItem(STORAGE_KEY) !== JSON.stringify(saved)) throw new Error()
      } catch {
        setBlocked(true)
        setError('Browser storage is unavailable. No sale was sent; contact the Owner before retrying.')
        return false
      }
      const attempt = { ...saved, payload: exactPayload, mode, protocol: fresh,
        reservationConfirmed: false, referenceAcknowledged: false }
      current.current = attempt
      setPending({ ...attempt })
      setStatus('unresolved')
      if (fresh === 'reserved_v1') await reserve(attempt, csrfToken)
      else await send(attempt, csrfToken)
      return true
    } catch {
      if (!current.current) {
        setProtocol('error')
        setError('Sales protocol or browser storage could not be verified. No sale was sent; contact the Owner if an attempt is uncertain.')
      }
      return false
    } finally {
      setWorking(false)
      busy.current = false
    }
  }

  async function reserve(attempt, csrfToken) {
    try {
      const response = await reserveSaleAttempt(attempt.mode === 'manual' ? 'Manual' : 'Direct',
        attempt.payload, attempt.key, csrfToken)
      if (!validReservation(response, attempt)) throw new Error('Reservation response mismatch')
      attempt.reservationConfirmed = true
      attempt.reference = attempt.mode === 'manual' ? response.manual_reference : response.direct_reference
      setPending({ ...attempt })
      if (attempt.mode === 'direct') {
        setStatus('reference_needed')
        setError('Record the Direct reference on the physical receipt/payment evidence before submitting.')
      } else await send(attempt, csrfToken)
    } catch (failure) {
      if (failure.status === 401) {
        try { await onRevalidateSession() } catch { /* Preserve pending key. */ }
      }
      setStatus('unresolved')
      setError('Reservation outcome is uncertain. Keep this UUID; retry the exact reservation or contact the Owner.')
    }
  }

  async function send(attempt, csrfToken) {
    try {
      const result = await (attempt.mode === 'manual' ? createManualSale : createSale)(
        attempt.payload, attempt.key, csrfToken)
      await check(attempt.key)
      // POST success is committed, but keep pending if status lookup cannot confirm it.
      return result
    } catch (failure) {
      if (failure.status === 401) {
        try { await onRevalidateSession() } catch { /* Preserve pending key. */ }
      }
      setStatus('unresolved')
      setError(failure.status === 403 ? 'Permission denied. The sale outcome is unresolved; contact the Owner.'
        : failure.status === 409 ? 'Idempotency conflict or changed sale data. Keep this key and contact the Owner.'
          : failure.status === 422 ? 'Sale was rejected. Keep this key and check its status before further action.'
            : 'Sale outcome is uncertain. Check status or retry this exact sale with the same key.')
    }
  }

  async function retry(csrfToken) {
    const attempt = current.current
    if (busy.current || blocked || !attempt?.payload || attempt.userId !== user.id ||
        (cancelledCheck?.key === attempt.key && cancelledCheck.userId === attempt.userId)) return
    try {
      if (sessionStorage.getItem(STORAGE_KEY) !== JSON.stringify({ key: attempt.key, userId: attempt.userId })) throw new Error()
    } catch {
      setBlocked(true)
      setError('Pending identifier is unavailable. Do not retry; contact the Owner.')
      return
    }
    busy.current = true
    setWorking(true)
    setError('')
    try {
      const fresh = await getSalesCapabilities()
      if (fresh !== attempt.protocol) {
        setError('Sales protocol changed. Do not retry; contact the Owner for reconciliation.')
        return
      }
      if (fresh === 'reserved_v1' && !attempt.reservationConfirmed) await reserve(attempt, csrfToken)
      else if (fresh === 'reserved_v1' && attempt.mode === 'direct' && !attempt.referenceAcknowledged) {
        setStatus('reference_needed')
        setError('Record and acknowledge the Direct reference before submitting.')
      } else await send(attempt, csrfToken)
    } catch {
      setError('Sales protocol could not be verified. Keep this key; do not start another sale.')
    } finally {
      busy.current = false
      setWorking(false)
    }
  }

  async function acknowledgeReference(csrfToken) {
    const attempt = current.current
    if (busy.current || blocked || !attempt?.payload || attempt.protocol !== 'reserved_v1' ||
        attempt.mode !== 'direct' || !attempt.reservationConfirmed || !attempt.reference ||
        attempt.userId !== user.id || cancelledCheck?.key === attempt.key) return
    busy.current = true
    setWorking(true)
    try {
      const saved = storedPending()
      if (saved.blocked || saved.pending?.key !== attempt.key || saved.pending.userId !== user.id ||
          await getSalesCapabilities() !== 'reserved_v1') throw new Error()
      attempt.referenceAcknowledged = true
      setPending({ ...attempt })
      await send(attempt, csrfToken)
    } catch {
      setError('Cannot verify this reserved attempt now. Keep the reference and contact the Owner if needed.')
    } finally {
      busy.current = false
      setWorking(false)
    }
  }

  function startNewSale() {
    if (blocked || busy.current || current.current || openAttempt || status !== 'committed' || !sale ||
        (protocol !== 'legacy' && protocol !== 'reserved_v1')) return false
    // A confirmed view must never bypass a browser-stored unresolved identifier.
    const saved = storedPending()
    if (saved.blocked || saved.pending) {
      setBlocked(true)
      setError('Pending sale state cannot be verified. Contact the Owner before another sale.')
      return false
    }
    setSale(null)
    setStatus('idle')
    setError('')
    return true
  }

  function clearAcknowledged(acknowledgment) {
    if (user.role !== 'Owner' || acknowledgment?.status !== 'committed' ||
        acknowledgment.sale?.recorded_by_user_id !== acknowledgment.recording_user_id ||
        !Number.isSafeInteger(acknowledgment.sale?.id) ||
        !UUID.test(acknowledgment.idempotency_key ?? '') || busy.current || working || blocked) return 'blocked'
    const expected = { key: acknowledgment.idempotency_key, userId: acknowledgment.recording_user_id }
    if (current.current?.key !== expected.key || current.current?.userId !== expected.userId) return 'no_match'
    try {
      if (sessionStorage.getItem(STORAGE_KEY) !== JSON.stringify(expected)) throw new Error()
      sessionStorage.removeItem(STORAGE_KEY)
      if (sessionStorage.getItem(STORAGE_KEY) !== null) throw new Error()
    } catch {
      setBlocked(true)
      setError('Acknowledged sale, but the matching browser pending identifier could not be cleared safely.')
      return 'blocked'
    }
    current.current = null
    setPending(null)
    setStatus('idle')
    setError('')
    setSale(null)
    return 'cleared'
  }

  async function checkCancelledAttempt() {
    const attempt = current.current
    if (busy.current || working || blocked || status === 'checking' ||
        protocol !== 'reserved_v1' || !attempt || attempt.userId !== user.id) return false
    if (!matchesPending(attempt)) {
      setBlocked(true)
      setError('Pending browser identifier changed or is unavailable. Contact the Owner; nothing was cleared.')
      return false
    }
    busy.current = true
    setWorking(true)
    setCancelledCheck(null)
    setError('')
    try {
      if (await getSalesCapabilities() !== 'reserved_v1') throw new Error('protocol_mismatch')
      const result = await getOwnSaleAttemptByKey(attempt.key)
      if (!mounted.current || !matchesPending(attempt) || protocolRef.current !== 'reserved_v1') {
        throw new Error('pending_changed')
      }
      if (result.state !== 'Cancelled' || result.user_id !== attempt.userId ||
          result.idempotency_key?.toLowerCase() !== attempt.key.toLowerCase() ||
          !Number.isSafeInteger(result.id) || result.id <= 0) {
        setError('This exact attempt is not confirmed Cancelled. Pending state remains blocked; contact the Owner.')
        return false
      }
      const keyStatus = await getSaleStatus(attempt.key)
      if (keyStatus.status !== 'not_committed_at_check') {
        setError('Sale key is processing or committed. Pending state remains blocked; contact the Owner.')
        return false
      }
      if (!mounted.current || !matchesPending(attempt) || protocolRef.current !== 'reserved_v1') {
        throw new Error('pending_changed')
      }
      setCancelledCheck({ key: attempt.key, userId: attempt.userId, id: result.id, attempt })
      return true
    } catch (failure) {
      if (failure.status === 401) {
        try { await onRevalidateSession() } catch { /* Keep pending state. */ }
      }
      if (mounted.current) setError(failure.status === 404
        ? 'No matching sale attempt was found for this account. Pending state was not cleared.'
        : 'Cancelled state could not be verified. Keep this key and contact the Owner.')
      return false
    } finally {
      busy.current = false
      if (mounted.current) setWorking(false)
    }
  }

  async function clearCancelledAttempt() {
    const checked = cancelledCheck
    const attempt = current.current
    if (busy.current || working || blocked || protocol !== 'reserved_v1' ||
        !checked || checked.attempt !== attempt || checked.key !== attempt?.key ||
        checked.userId !== attempt.userId) return false
    if (!matchesPending(attempt)) {
      setBlocked(true)
      setCancelledCheck(null)
      setError('Pending browser identifier changed or is unavailable. Contact the Owner; nothing was cleared.')
      return false
    }
    busy.current = true
    setWorking(true)
    setError('')
    try {
      if (await getSalesCapabilities() !== 'reserved_v1') throw new Error('protocol_mismatch')
      const result = await getOwnSaleAttemptByKey(attempt.key)
      if (result.state !== 'Cancelled' || result.id !== checked.id ||
          result.user_id !== attempt.userId ||
          result.idempotency_key?.toLowerCase() !== attempt.key.toLowerCase()) {
        throw new Error('attempt_changed')
      }
      const keyStatus = await getSaleStatus(attempt.key)
      if (keyStatus.status !== 'not_committed_at_check') throw new Error('sale_processing_or_committed')
      const open = await getOpenSaleAttempt()
      if (open !== null || !mounted.current || protocolRef.current !== 'reserved_v1' ||
          !matchesPending(attempt)) throw new Error('pending_changed')
      sessionStorage.removeItem(STORAGE_KEY)
      if (sessionStorage.getItem(STORAGE_KEY) !== null) throw new Error('storage_failure')
      current.current = null
      setPending(null)
      setCancelledCheck(null)
      setOpenAttempt(null)
      setSale(null)
      setStatus('idle')
      setError('')
      return true
    } catch (failure) {
      if (failure.status === 401) {
        try { await onRevalidateSession() } catch { /* Keep pending state. */ }
      }
      if (mounted.current) {
        if (failure.message === 'storage_failure' || failure.message === 'pending_changed') setBlocked(true)
        setCancelledCheck(null)
        setError('Cancelled-attempt clearance was not completed. Do not retry or start another sale; contact the Owner.')
      }
      return false
    } finally {
      busy.current = false
      if (mounted.current) setWorking(false)
    }
  }

  return { pending, blocked, status, sale, error, working, protocol, openAttempt, cancelledCheck,
    negotiate, submit, retry, check, acknowledgeReference, startNewSale, clearAcknowledged,
    checkCancelledAttempt, clearCancelledAttempt }
}
