import { useCallback, useEffect, useRef, useState } from 'react'

import { createManualSale, createSale, getSaleStatus } from './salesApi.js'

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

  const check = useCallback(async (key = current.current?.key) => {
    if (!key || blocked || current.current?.userId !== user.id) return
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
    if (busy.current || blocked || current.current) return false
    if (mode !== 'direct' && mode !== 'manual') return false
    busy.current = true
    setWorking(true)
    setError('')
    setSale(null)
    let saved
    try {
      saved = { key: crypto.randomUUID(), userId: user.id }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved))
      if (sessionStorage.getItem(STORAGE_KEY) !== JSON.stringify(saved)) throw new Error()
    } catch {
      setBlocked(true)
      setError('Browser storage is unavailable. No sale was sent; contact the Owner before retrying.')
      setWorking(false)
      busy.current = false
      return false
    }
    const attempt = { ...saved, payload, mode }
    current.current = attempt
    setPending(attempt)
    setStatus('unresolved')
    await send(attempt, csrfToken)
    return true
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
    } finally {
      busy.current = false
      setWorking(false)
    }
  }

  async function retry(csrfToken) {
    const attempt = current.current
    if (busy.current || blocked || !attempt?.payload || attempt.userId !== user.id) return
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
    await send(attempt, csrfToken)
  }

  function startNewSale() {
    if (blocked || busy.current || current.current || status !== 'committed' || !sale) return false
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

  return { pending, blocked, status, sale, error, working, submit, retry, check, startNewSale }
}
