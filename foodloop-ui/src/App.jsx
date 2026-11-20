import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useStore } from './store.jsx'
import { Toast } from './components/ui.jsx'
import Login, { HOME } from './pages/Login.jsx'
import Customer from './pages/Customer.jsx'
import Restaurant from './pages/Restaurant.jsx'
import Ngo from './pages/Ngo.jsx'
import Admin from './pages/Admin.jsx'

function Guard({ role, children }) {
  const { session } = useStore()
  if (!session) return <Navigate to="/" replace />
  if (session.role !== role) return <Navigate to={HOME[session.role]} replace />
  return children
}

export default function App() {
  const { session } = useStore()
  return (
    <>
      <Routes>
        <Route path="/" element={session ? <Navigate to={HOME[session.role]} replace /> : <Login />} />
        <Route path="/shop/*" element={<Guard role="customer"><Customer /></Guard>} />
        <Route path="/restaurant/*" element={<Guard role="restaurant"><Restaurant /></Guard>} />
        <Route path="/ngo/*" element={<Guard role="ngo"><Ngo /></Guard>} />
        <Route path="/admin/*" element={<Guard role="admin"><Admin /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toast />
    </>
  )
}
