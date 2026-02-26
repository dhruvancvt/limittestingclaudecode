import { useAppStore } from './store/appStore'
import LoginPage from './components/LoginPage'
import SessionsPage from './components/SessionsPage'
import TerminalPage from './components/TerminalPage'

export default function App() {
  const route = useAppStore((s) => s.route)

  return (
    <div className="app">
      {route === 'login' && <LoginPage />}
      {route === 'sessions' && <SessionsPage />}
      {route === 'terminal' && <TerminalPage />}
    </div>
  )
}
