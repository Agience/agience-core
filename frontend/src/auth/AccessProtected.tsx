import { Navigate } from "react-router-dom"

const AccessProtected = ({ children }: { children: React.ReactNode }) => {
  const hasAccess = localStorage.getItem('hasAccess') === 'true'
  if (!hasAccess) {
    return <Navigate to="/beta" replace />
  }
  return <>{children}</>
}

export default AccessProtected