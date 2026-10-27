import { useEffect, useRef } from 'react'

const ownerItems = [
  ['staff', 'Staff'], ['commissions', 'Commission Rules'], ['catalog', 'Catalog'],
  ['sales', 'Sales'], ['history', 'History'], ['reports', 'Reports'],
]
const cashierItems = ownerItems.filter(([id]) => ['sales', 'history', 'reports'].includes(id))

const iconPaths = {
  staff: <><circle cx="9" cy="8" r="3" /><path d="M3.5 20v-2a5.5 5.5 0 0 1 11 0v2M17 8h4m-2-2v4" /></>,
  commissions: <><circle cx="12" cy="12" r="9" /><path d="M15 9.5a3 3 0 0 0-6 0c0 3 6 1.5 6 5a3 3 0 0 1-6 0M12 5v2m0 10v2" /></>,
  catalog: <><path d="M4 4h16v16H4zM4 10h16M10 4v16" /></>,
  sales: <><path d="M5 3h14v18l-3-2-4 2-4-2-3 2zM8 9h8m-8 4h6" /></>,
  history: <><path d="M3 12a9 9 0 1 0 2.5-6.2M3 4v4h4M12 7v5l3 2" /></>,
  reports: <><path d="M4 20h16M6 16v-5m6 5V5m6 11V9" /></>,
}

function Links({ role, section, onSelect }) {
  return <nav className="app-nav-links" aria-label={`${role} sections`}>
    {(role === 'Owner' ? ownerItems : cashierItems).map(([id, label]) =>
      <button key={id} type="button" aria-pressed={section === id} onClick={() => onSelect(id)}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{iconPaths[id]}</svg>
        <span>{label}</span>
      </button>)}
  </nav>
}

export default function AppNavigation({ role, section, onSelect, mobile, open, onClose }) {
  const dialogRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    if (!mobile || !open) return undefined
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    dialog.showModal()
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      if (dialog.open) dialog.close()
    }
  }, [mobile, open])

  if (!mobile) {
    return <aside className="app-sidebar" aria-label="Application sidebar">
      <img className="app-sidebar-logo" src="/assets/yabs-logo.png" alt="Yab's Hair and Beauty Studio" />
      <Links role={role} section={section} onSelect={onSelect} />
    </aside>
  }

  return <dialog className="app-drawer" ref={dialogRef} aria-label="Application navigation"
    onCancel={(event) => { event.preventDefault(); onClose() }}>
    <div className="app-drawer-heading">
      <img className="app-sidebar-logo" src="/assets/yabs-logo.png" alt="Yab's Hair and Beauty Studio" />
      <button ref={closeRef} className="app-drawer-close" type="button" onClick={onClose}
        aria-label="Close menu">×</button>
    </div>
    <Links role={role} section={section} onSelect={(id) => { onClose(); onSelect(id) }} />
  </dialog>
}
