import { useEffect, useRef, useState } from 'react'

import { changeCommissionRuleStatus, createCommissionRule, getCommissionRules } from './commissionRulesApi.js'
import './CommissionRulesManagement.css'

function errorMessage(error) {
  if (error.status === 403) return 'You do not have permission to manage commission rules.'
  if (error.status === 422) return 'Please check the rule information and try again.'
  if (error.status === 404) return 'This rule was not found. Refresh the list and try again.'
  return 'Commission Rules is temporarily unavailable. Please try again.'
}

function valueErrorFor(raw, type) {
  const value = raw.trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return 'Enter a positive value with at most two decimal places.'
  const [integer, fraction = ''] = value.split('.')
  const significant = integer.replace(/^0+/, '') || '0'
  if (significant.length > 10) return 'Enter at most ten digits before the decimal point.'
  const cents = BigInt(significant) * 100n + BigInt(fraction.padEnd(2, '0') || '0')
  if (cents === 0n) return 'Value must be greater than zero.'
  if (type === 'Percentage' && cents > 10000n) return 'Percentage must not exceed 100.'
  return ''
}

function displayValue(rule) {
  const [integer, fraction = ''] = String(rule.value).split('.')
  if (rule.type === 'Percentage') {
    const decimal = fraction.replace(/0+$/, '')
    return `${integer}${decimal ? `.${decimal}` : ''}%`
  }
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `₱${grouped}.${fraction.padEnd(2, '0')}`
}

export default function CommissionRulesManagement({ csrfToken, onRevalidateSession }) {
  const [rules, setRules] = useState([])
  const [state, setState] = useState('loading')
  const [message, setMessage] = useState('')
  const [messageRole, setMessageRole] = useState('status')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const [name, setName] = useState('')
  const [type, setType] = useState('')
  const [value, setValue] = useState('')
  const [errors, setErrors] = useState({})
  const [addError, setAddError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingId, setPendingId] = useState(null)
  const [confirmRule, setConfirmRule] = useState(null)
  const [confirmError, setConfirmError] = useState('')
  const addDialog = useRef(null)
  const confirmDialog = useRef(null)
  const addButton = useRef(null)
  const pending = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    getCommissionRules(controller.signal).then((result) => {
      if (controller.signal.aborted) return
      setRules(result)
      setState('ready')
      setMessage('')
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) {
        setState('error')
        setMessage(errorMessage(error))
      }
    })
    return () => controller.abort()
  }, [loadAttempt, onRevalidateSession])

  useEffect(() => {
    if (addOpen && !addDialog.current.open) addDialog.current.showModal()
    if (!addOpen && addDialog.current?.open) addDialog.current.close()
  }, [addOpen])

  useEffect(() => {
    if (confirmRule && !confirmDialog.current.open) confirmDialog.current.showModal()
    if (!confirmRule && confirmDialog.current?.open) confirmDialog.current.close()
  }, [confirmRule])

  async function handleRequestError(error, report) {
    if (error.status === 401) {
      try { if (!await onRevalidateSession()) return } catch { /* Do not claim logout on a temporary /me failure. */ }
    }
    report(errorMessage(error))
  }

  function openAdd() {
    setName('')
    setType('')
    setValue('')
    setErrors({})
    setAddError('')
    setAddOpen(true)
  }

  function closeAdd() {
    if (pending.current) return
    setAddOpen(false)
    addButton.current?.focus()
  }

  async function submitAdd(event) {
    event.preventDefault()
    if (pending.current) return
    const cleanName = name.trim()
    const nextErrors = {
      name: cleanName ? '' : 'Enter a rule name.',
      type: ['Percentage', 'Fixed'].includes(type) ? '' : 'Select a type.',
      value: valueErrorFor(value, type),
    }
    setErrors(nextErrors)
    if (Object.values(nextErrors).some(Boolean)) return
    pending.current = true
    setSaving(true)
    setAddError('')
    try {
      const created = await createCommissionRule(cleanName, type, value.trim(), csrfToken)
      setRules((current) => [...current, created])
      setAddOpen(false)
      setMessage('Commission rule added.')
      setMessageRole('status')
      addButton.current?.focus()
    } catch (error) {
      await handleRequestError(error, setAddError)
    } finally {
      pending.current = false
      setSaving(false)
    }
  }

  async function updateStatus(rule, active) {
    if (pending.current) return
    pending.current = true
    setPendingId(rule.id)
    setMessage('')
    setConfirmError('')
    try {
      const updated = await changeCommissionRuleStatus(rule.id, active, csrfToken)
      setRules((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMessage(`${updated.name} ${updated.active ? 'activated' : 'deactivated'}.`)
      setMessageRole('status')
      setConfirmRule(null)
    } catch (error) {
      if (error.status === 409 && !active) {
        setConfirmError('Cannot deactivate: an active Service or Product still references this rule.')
      } else {
        if (active) setMessageRole('alert')
        await handleRequestError(error, active ? setMessage : setConfirmError)
      }
    } finally {
      pending.current = false
      setPendingId(null)
    }
  }

  const orderedRules = [...rules].sort((a, b) => a.id - b.id)

  return (
    <section className="commission-rules" aria-labelledby="commission-rules-heading">
      <div className="commission-heading-row">
        <div><h1 id="commission-rules-heading">Commission Rules</h1><p>Manage commission rules for future sales.</p></div>
        <button ref={addButton} className="commission-primary" type="button"
          onClick={openAdd} disabled={state !== 'ready' || pendingId !== null}>Add Rule</button>
      </div>
      {state === 'loading' && <p role="status">Loading commission rules…</p>}
      {state === 'error' && <div role="alert"><p>{message}</p><button type="button" onClick={() => {
        setState('loading')
        setLoadAttempt((attempt) => attempt + 1)
      }}>Try again</button></div>}
      {state === 'ready' && <>
        {message && <p className="commission-feedback" role={messageRole} aria-live="polite">{message}</p>}
        <div className="commission-results">
          {orderedRules.length === 0 ? <p className="commission-empty">No commission rules yet.</p> :
            <table className="commission-table"><thead><tr>
              <th scope="col">Name</th><th scope="col">Type</th><th scope="col">Value</th>
              <th scope="col">Status</th><th scope="col">Action</th>
            </tr></thead><tbody>{orderedRules.map((rule) => <tr key={rule.id}>
              <td data-label="Name">{rule.name}</td><td data-label="Type">{rule.type}</td>
              <td data-label="Value">{displayValue(rule)}</td>
              <td data-label="Status">{rule.active ? 'Active' : 'Inactive'}</td>
              <td data-label="Action"><button type="button" disabled={pendingId !== null || saving}
                aria-busy={pendingId === rule.id}
                aria-label={`${rule.active ? 'Deactivate' : 'Activate'} ${rule.name}`}
                onClick={() => {
                  if (rule.active) { setConfirmError(''); setConfirmRule(rule) }
                  else updateStatus(rule, true)
                }}>{pendingId === rule.id ? 'Updating…' : rule.active ? 'Deactivate' : 'Activate'}</button></td>
            </tr>)}</tbody></table>}
        </div>
      </>}

      <dialog ref={addDialog} aria-labelledby="add-rule-heading" onCancel={(event) => {
        if (saving) event.preventDefault()
        else closeAdd()
      }} onClose={() => setAddOpen(false)}>
        <form className="commission-form" onSubmit={submitAdd} noValidate>
          <h2 id="add-rule-heading">Add Rule</h2>
          <label htmlFor="rule-name">Rule Name</label>
          <input id="rule-name" autoFocus value={name} required disabled={saving}
            aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? 'rule-name-error' : undefined}
            onChange={(event) => { setName(event.target.value); setErrors((current) => ({ ...current, name: '' })) }} />
          {errors.name && <p id="rule-name-error" role="alert">{errors.name}</p>}
          <label htmlFor="rule-type">Type</label>
          <select id="rule-type" value={type} required disabled={saving}
            aria-invalid={Boolean(errors.type)} aria-describedby={errors.type ? 'rule-type-error' : undefined}
            onChange={(event) => { setType(event.target.value); setErrors((current) => ({ ...current, type: '' })) }}>
            <option value="">Select type</option><option value="Percentage">Percentage</option><option value="Fixed">Fixed</option>
          </select>
          {errors.type && <p id="rule-type-error" role="alert">{errors.type}</p>}
          <label htmlFor="rule-value">Value</label>
          <input id="rule-value" type="text" inputMode="decimal" value={value} required disabled={saving}
            aria-invalid={Boolean(errors.value)} aria-describedby={errors.value ? 'rule-value-error' : undefined}
            onChange={(event) => { setValue(event.target.value); setErrors((current) => ({ ...current, value: '' })) }} />
          {errors.value && <p id="rule-value-error" role="alert">{errors.value}</p>}
          {addError && <p role="alert">{addError}</p>}
          <div className="commission-dialog-actions"><button type="button" onClick={closeAdd} disabled={saving}>Cancel</button>
            <button className="commission-primary" type="submit" disabled={saving} aria-busy={saving}>
              {saving ? 'Saving…' : 'Save'}</button></div>
        </form>
      </dialog>

      <dialog ref={confirmDialog} aria-labelledby="deactivate-rule-heading" onCancel={(event) => {
        if (pending.current) event.preventDefault()
        else setConfirmRule(null)
      }} onClose={() => setConfirmRule(null)}>
        <h2 id="deactivate-rule-heading">Deactivate rule?</h2>
        <p>Deactivate {confirmRule?.name}? This will not change historical commission snapshots.</p>
        {confirmError && <p role="alert">{confirmError}</p>}
        <div className="commission-dialog-actions"><button type="button" disabled={pendingId !== null}
          onClick={() => setConfirmRule(null)}>Cancel</button>
          <button type="button" className="commission-primary" disabled={pendingId !== null}
            onClick={() => updateStatus(confirmRule, false)}>Confirm deactivation</button></div>
      </dialog>
    </section>
  )
}
