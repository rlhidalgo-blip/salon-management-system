import { useEffect, useMemo, useRef, useState } from 'react'

import { addStaff, changeStaffStatus, getStaff } from './staffApi.js'
import './StaffManagement.css'

function requestMessage(error) {
  if (error.status === 403) return 'You do not have permission to manage staff.'
  if (error.status === 422) return 'Please check the staff information and try again.'
  if (error.status === 404) return 'This staff member was not found. Refresh the list and try again.'
  return 'Staff Management is temporarily unavailable. Please try again.'
}

export default function StaffManagement({ csrfToken, onRevalidateSession }) {
  const [staff, setStaff] = useState([])
  const [state, setState] = useState('loading')
  const [message, setMessage] = useState('')
  const [messageKind, setMessageKind] = useState('status')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [nameError, setNameError] = useState('')
  const [roleError, setRoleError] = useState('')
  const [dialogError, setDialogError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingId, setPendingId] = useState(null)
  const [confirmStaff, setConfirmStaff] = useState(null)
  const [confirmError, setConfirmError] = useState('')
  const addDialog = useRef(null)
  const confirmDialog = useRef(null)
  const addButton = useRef(null)
  const pending = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    getStaff(controller.signal).then((records) => {
      if (controller.signal.aborted) return
      setStaff(records)
      setState('ready')
      setMessage('')
      setMessageKind('status')
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try {
          if (!await onRevalidateSession()) return
        } catch { /* Keep the screen and offer retry when /me is unavailable. */ }
      }
      if (!controller.signal.aborted) {
        setState('error')
        setMessage(requestMessage(error))
      }
    })
    return () => controller.abort()
  }, [onRevalidateSession])

  // Native dialogs provide focus trapping, Escape, and focus restoration.
  useEffect(() => {
    if (dialogOpen && !addDialog.current.open) addDialog.current.showModal()
    if (!dialogOpen && addDialog.current?.open) addDialog.current.close()
  }, [dialogOpen])

  useEffect(() => {
    if (confirmStaff && !confirmDialog.current.open) confirmDialog.current.showModal()
    if (!confirmStaff && confirmDialog.current?.open) confirmDialog.current.close()
  }, [confirmStaff])

  const visibleStaff = useMemo(() => staff
    .filter((person) => person.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
    .filter((person) => statusFilter === 'all' || person.active === (statusFilter === 'active'))
    .sort((a, b) => a.id - b.id), [staff, search, statusFilter])

  async function handleUnauthorized(error, setError) {
    if (error.status === 401) {
      try {
        if (!await onRevalidateSession()) return
      } catch { /* A temporary /me failure must not be treated as logout. */ }
    }
    if (setError === setMessage) setMessageKind('alert')
    setError(requestMessage(error))
  }

  function openAdd() {
    setName('')
    setRole('')
    setNameError('')
    setRoleError('')
    setDialogError('')
    setDialogOpen(true)
  }

  function closeAdd() {
    if (pending.current) return
    setDialogOpen(false)
    addButton.current?.focus()
  }

  function requestStatusChange(person) {
    if (!person.active) return updateStatus(person, true)
    setConfirmError('')
    setConfirmStaff(person)
  }

  async function submitAdd(event) {
    event.preventDefault()
    if (pending.current) return
    const trimmed = name.trim()
    setNameError(trimmed ? '' : 'Enter a staff name.')
    setRoleError(role === 'Barber' || role === 'Stylist' ? '' : 'Select a role.')
    if (!trimmed || !['Barber', 'Stylist'].includes(role)) return
    pending.current = true
    setSaving(true)
    setDialogError('')
    try {
      const created = await addStaff(trimmed, role, csrfToken)
      setStaff((records) => [...records, created])
      setDialogOpen(false)
      setMessage('Staff member added.')
      setMessageKind('status')
      addButton.current?.focus()
    } catch (error) {
      await handleUnauthorized(error, setDialogError)
    } finally {
      pending.current = false
      setSaving(false)
    }
  }

  async function updateStatus(person, active) {
    if (pending.current) return
    pending.current = true
    setPendingId(person.id)
    setMessage('')
    setConfirmError('')
    try {
      const updated = await changeStaffStatus(person.id, active, csrfToken)
      setStaff((records) => records.map((record) => record.id === updated.id ? updated : record))
      setMessage(`${updated.name} ${updated.active ? 'activated' : 'deactivated'}.`)
      setMessageKind('status')
      setConfirmStaff(null)
    } catch (error) {
      await handleUnauthorized(error, active ? setMessage : setConfirmError)
    } finally {
      pending.current = false
      setPendingId(null)
    }
  }

  return (
    <section className="staff-management" aria-labelledby="staff-heading">
      <div className="staff-heading-row">
        <div><h2 id="staff-heading">Staff Management</h2><p>Manage your barbers and stylists.</p></div>
        <button ref={addButton} type="button" className="staff-primary" onClick={openAdd} disabled={state !== 'ready' || pendingId !== null}>Add Staff</button>
      </div>
      {state === 'loading' && <p role="status">Loading staff…</p>}
      {state === 'error' && <div role="alert"><p>{message}</p><button type="button" onClick={() => {
        setState('loading')
        // Explicit retry uses a fresh request without altering auth state.
        getStaff().then((records) => { setStaff(records); setState('ready'); setMessage('') })
          .catch(async (error) => {
            if (error.status === 401) {
              try { if (!await onRevalidateSession()) return } catch { /* Retry remains available. */ }
            }
            setState('error')
            setMessage(requestMessage(error))
          })
      }}>Try again</button></div>}
      {state === 'ready' && <>
        <div className="staff-controls">
          <label>Name
            <span className="staff-search-field">
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
        {message && <p className="staff-feedback" role={messageKind} aria-live="polite">{message}</p>}
        <div className="staff-results">
          {visibleStaff.length === 0 ?
            <p className="staff-empty">{staff.length === 0 ? 'No staff members yet.' : 'No staff match your search or filter.'}</p> :
            <table className="staff-table"><thead><tr><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Action</th></tr></thead>
              <tbody>{visibleStaff.map((person) => <tr key={person.id}>
                <td data-label="Name">{person.name}</td><td data-label="Role">{person.role}</td>
                <td data-label="Status"><span className={`staff-status ${person.active ? 'staff-status--active' : ''}`}>{person.active ? 'Active' : 'Inactive'}</span></td>
                <td data-label="Action"><button type="button" disabled={pendingId !== null || saving}
                  aria-busy={pendingId === person.id}
                  onClick={() => requestStatusChange(person)}>
                  {pendingId === person.id ? 'Updating…' : person.active ? 'Deactivate' : 'Activate'}
                </button></td>
              </tr>)}</tbody></table>}
        </div>
      </>}

      <dialog ref={addDialog} aria-labelledby="add-staff-heading" onCancel={(event) => {
        if (saving) event.preventDefault()
        else closeAdd()
      }} onClose={() => setDialogOpen(false)}>
        <form className="staff-dialog-form" onSubmit={submitAdd} noValidate>
          <h3 id="add-staff-heading">Add Staff</h3>
          <label htmlFor="staff-name">Staff Name</label>
          <input id="staff-name" autoFocus value={name} onChange={(event) => { setName(event.target.value); setNameError('') }}
            aria-invalid={Boolean(nameError)} aria-describedby={nameError ? 'staff-name-error' : undefined} disabled={saving} required />
          {nameError && <p id="staff-name-error" role="alert">{nameError}</p>}
          <label htmlFor="staff-role">Role</label>
          <select id="staff-role" value={role} onChange={(event) => { setRole(event.target.value); setRoleError('') }}
            aria-invalid={Boolean(roleError)} aria-describedby={roleError ? 'staff-role-error' : undefined} disabled={saving} required>
            <option value="">Select role</option><option value="Barber">Barber</option><option value="Stylist">Stylist</option>
          </select>
          {roleError && <p id="staff-role-error" role="alert">{roleError}</p>}
          {dialogError && <p role="alert">{dialogError}</p>}
          <div className="staff-dialog-actions"><button type="button" onClick={closeAdd} disabled={saving}>Cancel</button>
            <button className="staff-primary" type="submit" disabled={saving} aria-busy={saving}>{saving ? 'Saving…' : 'Save'}</button></div>
        </form>
      </dialog>

      <dialog ref={confirmDialog} aria-labelledby="deactivate-heading" onCancel={(event) => {
        if (pending.current) event.preventDefault()
        else setConfirmStaff(null)
      }} onClose={() => setConfirmStaff(null)}>
        <h3 id="deactivate-heading">Deactivate staff?</h3>
        <p>Deactivate {confirmStaff?.name}? This keeps their historical records.</p>
        {confirmError && <p role="alert">{confirmError}</p>}
        <div className="staff-dialog-actions"><button type="button" onClick={() => setConfirmStaff(null)} disabled={pendingId !== null}>Cancel</button>
          <button type="button" className="staff-primary" disabled={pendingId !== null}
            onClick={() => updateStatus(confirmStaff, false)}>Confirm deactivation</button></div>
      </dialog>
    </section>
  )
}
