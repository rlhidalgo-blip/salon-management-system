import LoginPage from '../features/auth/LoginPage.jsx'
import { useTheme } from './useTheme.js'

export default function App() {
  const [theme, toggleTheme] = useTheme()

  return <LoginPage theme={theme} onToggleTheme={toggleTheme} />
}
