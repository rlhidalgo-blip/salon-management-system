import { useEffect, useMemo, useRef, useState } from 'react'

import { getCommissionRules } from '../commissions/commissionRulesApi.js'
import { changeCatalogItemStatus, createCatalogItem, getCatalogItems, updateCatalogItem } from './catalogApi.js'
import './CatalogManagement.css'

const kindTitle = (kind) => kind === 'services' ? 'Service' : 'Product'
const requiredRuleType = (kind) => kind === 'services' ? 'Percentage' : 'Fixed'

function cents(raw) {
  const value = raw.trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null
  const [integer, fraction = ''] = value.split('.')
  const significant = integer.replace(/^0+/, '') || '0'
  if (significant.length > 10) return null
  return BigInt(significant) * 100n + BigInt(fraction.padEnd(2, '0') || '0')
}

function money(raw) {
  const [integer, fraction = ''] = String(raw).split('.')
  return `₱${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`
}

function requestMessage(error) {
  if (error.status === 403) return 'You do not have permission to manage the catalog.'
  if (error.status === 404) return 'This item or commission rule was not found. Refresh and try again.'
  if (error.status === 409) return 'The item or commission rule changed. Refresh and try again.'
  if (error.status === 422) return 'Please check the catalog information and try again.'
  return 'Catalog is temporarily unavailable. Please try again.'
}

function CatalogFormDialog({ kind, item, rules, onSave, onClose, onRequestError }) {
  const dialog = useRef(null)
  const pending = useRef(false)
  const [name, setName] = useState(item?.name ?? '')
  const [price, setPrice] = useState(item?.current_price ?? '')
  const [ruleId, setRuleId] = useState(String(item?.commission_rule_id ?? ''))
  const [variable, setVariable] = useState(item?.allows_variable_price ?? false)
  const [errors, setErrors] = useState({})
  const [requestError, setRequestError] = useState('')
  const [saving, setSaving] = useState(false)
  const expectedType = requiredRuleType(kind)
  const compatible = rules.filter((rule) => rule.active && rule.type === expectedType)
  const currentRule = rules.find((rule) => rule.id === item?.commission_rule_id)
  const inactiveCurrent = item && currentRule && !currentRule.active

  useEffect(() => {
    dialog.current.showModal()
    return () => { if (dialog.current?.open) dialog.current.close() }
  }, [])

  function validate() {
    const selectedRule = rules.find((rule) => String(rule.id) === ruleId)
    const priceCents = cents(price)
    const next = {
      name: name.trim() ? '' : 'Enter a name.',
      price: priceCents !== null && priceCents > 0n ? '' : 'Enter a positive price with at most two decimal places and ten integer digits.',
      rule: !selectedRule ? 'Select a commission rule.'
        : selectedRule.type !== expectedType ? `Select a ${expectedType} rule.`
          : (!selectedRule.active && (!item || selectedRule.id !== item.commission_rule_id)) ? 'Select an active commission rule.' : '',
    }
    if (!next.price && !next.rule && kind === 'products' && (item?.active ?? true) &&
        selectedRule.value && priceCents < cents(String(selectedRule.value))) {
      next.price = 'Price must cover the fixed commission.'
    }
    setErrors(next)
    return Object.values(next).every((message) => !message)
  }

  async function submit(event) {
    event.preventDefault()
    if (pending.current || !validate()) return
    const cleanPrice = price.trim()
    const values = item ? {} : {
      name: name.trim(), current_price: cleanPrice, commission_rule_id: Number(ruleId),
      ...(kind === 'services' ? { allows_variable_price: variable } : {}),
    }
    if (item) {
      if (name.trim() !== item.name) values.name = name.trim()
      if (cents(cleanPrice) !== cents(String(item.current_price))) values.current_price = cleanPrice
      if (Number(ruleId) !== item.commission_rule_id) values.commission_rule_id = Number(ruleId)
      if (kind === 'services' && variable !== item.allows_variable_price) values.allows_variable_price = variable
      if (Object.keys(values).length === 0) {
        setRequestError('Make a change before saving.')
        return
      }
    }
    pending.current = true
    setSaving(true)
    setRequestError('')
    try {
      await onSave(values)
      onClose()
    } catch (error) {
      const message = await onRequestError(error)
      if (message) setRequestError(message)
    } finally {
      pending.current = false
      setSaving(false)
    }
  }

  const heading = `${item ? 'Edit' : 'Add'} ${kindTitle(kind)}`
  return <dialog ref={dialog} aria-labelledby="catalog-form-heading" onCancel={(event) => {
    if (pending.current) event.preventDefault()
    else onClose()
  }} onClose={onClose}>
    <form className="catalog-form" onSubmit={submit} noValidate>
      <h2 id="catalog-form-heading">{heading}</h2>
      <label htmlFor="catalog-name">Name</label>
      <input id="catalog-name" autoFocus required disabled={saving} value={name}
        aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? 'catalog-name-error' : undefined}
        onChange={(event) => { setName(event.target.value); setErrors((old) => ({ ...old, name: '' })) }} />
      {errors.name && <p id="catalog-name-error" role="alert">{errors.name}</p>}
      <label htmlFor="catalog-price">Current Price</label>
      <input id="catalog-price" type="text" inputMode="decimal" required disabled={saving} value={price}
        aria-invalid={Boolean(errors.price)} aria-describedby={errors.price ? 'catalog-price-error' : undefined}
        onChange={(event) => { setPrice(event.target.value); setErrors((old) => ({ ...old, price: '' })) }} />
      {errors.price && <p id="catalog-price-error" role="alert">{errors.price}</p>}
      <label htmlFor="catalog-rule">Commission Rule</label>
      <select id="catalog-rule" required disabled={saving} value={ruleId}
        aria-invalid={Boolean(errors.rule)} aria-describedby={errors.rule ? 'catalog-rule-error' : undefined}
        onChange={(event) => { setRuleId(event.target.value); setErrors((old) => ({ ...old, rule: '' })) }}>
        <option value="">Select an active {expectedType} rule</option>
        {inactiveCurrent && <option value={currentRule.id} disabled>{currentRule.name} (Inactive)</option>}
        {compatible.map((rule) => <option key={rule.id} value={rule.id}>{rule.name}</option>)}
      </select>
      {compatible.length === 0 && <p className="catalog-note">No active {expectedType} rules are available. Create one in Commission Rules before adding or reassigning.</p>}
      {errors.rule && <p id="catalog-rule-error" role="alert">{errors.rule}</p>}
      {kind === 'services' && <label className="catalog-checkbox">
        <input type="checkbox" checked={variable} disabled={saving}
          onChange={(event) => setVariable(event.target.checked)} />Allow Variable Pricing
      </label>}
      {requestError && <p role="alert">{requestError}</p>}
      <div className="catalog-dialog-actions">
        <button type="button" disabled={saving} onClick={onClose}>Cancel</button>
        <button className="catalog-primary" type="submit" disabled={saving} aria-busy={saving}>{saving ? 'Saving…' : 'Save'}</button>
      </div>
    </form>
  </dialog>
}

export default function CatalogManagement({ csrfToken, onRevalidateSession }) {
  const [tab, setTab] = useState('services')
  const [items, setItems] = useState({ services: [], products: [] })
  const [rules, setRules] = useState([])
  const [state, setState] = useState('loading')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [message, setMessage] = useState('')
  const [messageRole, setMessageRole] = useState('status')
  const [editing, setEditing] = useState(null)
  const [confirmItem, setConfirmItem] = useState(null)
  const [confirmError, setConfirmError] = useState('')
  const [pendingId, setPendingId] = useState(null)
  const pending = useRef(false)
  const confirmDialog = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      getCatalogItems('services', controller.signal),
      getCatalogItems('products', controller.signal),
      getCommissionRules(controller.signal),
    ]).then(([services, products, nextRules]) => {
      if (controller.signal.aborted) return
      setItems({ services, products })
      setRules(nextRules)
      setState('ready')
      setMessage('')
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) {
        setState('error')
        setMessage(requestMessage(error))
      }
    })
    return () => controller.abort()
  }, [loadAttempt, onRevalidateSession])

  useEffect(() => {
    if (confirmItem && !confirmDialog.current.open) confirmDialog.current.showModal()
    if (!confirmItem && confirmDialog.current?.open) confirmDialog.current.close()
  }, [confirmItem])

  const visible = useMemo(() => items[tab]
    .filter((item) => item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
    .filter((item) => statusFilter === 'all' || item.active === (statusFilter === 'active'))
    .sort((a, b) => a.id - b.id), [items, tab, search, statusFilter])

  async function onRequestError(error) {
    if (error.status === 401) {
      try { if (!await onRevalidateSession()) return null } catch { /* Temporary /me failure is not logout. */ }
    }
    return requestMessage(error)
  }

  function replaceItem(kind, updated) {
    setItems((current) => ({ ...current, [kind]: current[kind].map((item) => item.id === updated.id ? updated : item) }))
  }

  async function save(values) {
    const kind = editing.kind
    const updated = editing.item
      ? await updateCatalogItem(kind, editing.item.id, values, csrfToken)
      : await createCatalogItem(kind, values, csrfToken)
    if (editing.item) replaceItem(kind, updated)
    else setItems((current) => ({ ...current, [kind]: [...current[kind], updated] }))
    setMessage(`${kindTitle(kind)} ${editing.item ? 'updated' : 'added'}.`)
    setMessageRole('status')
  }

  async function updateStatus(item, active) {
    if (pending.current) return
    const rule = rules.find((candidate) => candidate.id === item.commission_rule_id)
    if (active && (!rule?.active || rule.type !== requiredRuleType(tab))) {
      setMessageRole('alert')
      setMessage('Assign an active compatible commission rule before reactivating.')
      return
    }
    if (active && tab === 'products' && cents(String(rule.value)) > cents(String(item.current_price))) {
      setMessageRole('alert')
      setMessage('Product price must cover its fixed commission before reactivating.')
      return
    }
    pending.current = true
    setPendingId(item.id)
    setMessage('')
    setConfirmError('')
    try {
      const updated = await changeCatalogItemStatus(tab, item.id, active, csrfToken)
      replaceItem(tab, updated)
      setConfirmItem(null)
      setMessage(`${updated.name} ${active ? 'activated' : 'deactivated'}.`)
      setMessageRole('status')
    } catch (error) {
      const nextMessage = await onRequestError(error)
      if (nextMessage) {
        if (active) { setMessage(nextMessage); setMessageRole('alert') }
        else setConfirmError(nextMessage)
      }
    } finally {
      pending.current = false
      setPendingId(null)
    }
  }

  function switchTab(next) {
    setTab(next)
    setSearch('')
    setStatusFilter('all')
    setMessage('')
  }

  const title = kindTitle(tab)
  return <section className="catalog-management" aria-labelledby="catalog-heading">
    <div className="catalog-heading-row">
      <div><h1 id="catalog-heading">Catalog Management</h1><p>Manage services and products for future sales.</p></div>
      <button className="catalog-primary" type="button" disabled={state !== 'ready' || pendingId !== null}
        onClick={(event) => setEditing({ kind: tab, item: null, trigger: event.currentTarget })}>Add {title}</button>
    </div>
    <nav className="catalog-tabs" aria-label="Catalog types">
      <button type="button" aria-pressed={tab === 'services'} onClick={() => switchTab('services')}>Services</button>
      <button type="button" aria-pressed={tab === 'products'} onClick={() => switchTab('products')}>Products</button>
    </nav>
    {state === 'loading' && <p role="status">Loading catalog…</p>}
    {state === 'error' && <div role="alert"><p>{message}</p><button type="button" onClick={() => {
      setState('loading'); setLoadAttempt((count) => count + 1)
    }}>Try again</button></div>}
    {state === 'ready' && <>
      <div className="catalog-controls">
        <label>Name
          <span className="catalog-search-field">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" />
            </svg>
            <input type="search" placeholder="Search" value={search} onChange={(event) => setSearch(event.target.value)} />
          </span>
        </label>
        <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">All</option><option value="active">Active</option><option value="inactive">Inactive</option>
        </select></label>
      </div>
      {message && <p className="catalog-feedback" role={messageRole} aria-live="polite">{message}</p>}
      <div className="catalog-results">
        {visible.length === 0 ? <p className="catalog-empty">{items[tab].length === 0
          ? `No ${tab} yet.` : 'No items match your search or filter.'}</p> :
          <table className="catalog-table"><thead><tr>
            <th scope="col">Name</th><th scope="col">Price</th><th scope="col">Commission Rule</th>
            <th scope="col">Status</th><th scope="col">Action</th>
          </tr></thead><tbody>{visible.map((item) => {
            const rule = rules.find((candidate) => candidate.id === item.commission_rule_id)
            return <tr key={item.id}>
              <td data-label="Name">{item.name}</td>
              <td data-label="Price">{money(item.current_price)}</td>
              <td data-label="Commission Rule">{rule ? `${rule.name}${rule.active ? '' : ' (Inactive)'}` : 'Rule unavailable'}</td>
              <td data-label="Status">{item.active ? 'Active' : 'Inactive'}</td>
              <td data-label="Action"><div className="catalog-row-actions">
                <button type="button" disabled={pendingId !== null} aria-label={`Edit ${item.name}`}
                  onClick={(event) => setEditing({ kind: tab, item, trigger: event.currentTarget })}>Edit</button>
                <button type="button" disabled={pendingId !== null} aria-busy={pendingId === item.id}
                  aria-label={`${item.active ? 'Deactivate' : 'Activate'} ${item.name}`}
                  onClick={() => item.active ? (setConfirmError(''), setConfirmItem(item)) : updateStatus(item, true)}>
                  {pendingId === item.id ? 'Updating…' : item.active ? 'Deactivate' : 'Activate'}</button>
              </div></td>
            </tr>
          })}</tbody></table>}
      </div>
    </>}
    {editing && <CatalogFormDialog key={`${editing.kind}-${editing.item?.id ?? 'new'}`}
      kind={editing.kind} item={editing.item} rules={rules} onSave={save}
      onRequestError={onRequestError} onClose={() => { editing.trigger?.focus(); setEditing(null) }} />}
    <dialog ref={confirmDialog} aria-labelledby="catalog-deactivate-heading" onCancel={(event) => {
      if (pending.current) event.preventDefault()
      else setConfirmItem(null)
    }} onClose={() => setConfirmItem(null)}>
      <h2 id="catalog-deactivate-heading">Deactivate {title.toLowerCase()}?</h2>
      <p>Deactivate {confirmItem?.name}? Historical transaction records will remain unchanged.</p>
      {confirmError && <p role="alert">{confirmError}</p>}
      <div className="catalog-dialog-actions"><button type="button" disabled={pendingId !== null}
        onClick={() => setConfirmItem(null)}>Cancel</button>
        <button className="catalog-primary" type="button" disabled={pendingId !== null}
          onClick={() => updateStatus(confirmItem, false)}>Confirm deactivation</button></div>
    </dialog>
  </section>
}
