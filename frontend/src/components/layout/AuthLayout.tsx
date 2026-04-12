/**
 * components/layout/AuthLayout.tsx
 *
 * Shared animated background + centered card layout used by Login and SetupWizard.
 * Animated blobs + conic gradient, frosted-glass card, Agience logo.
 */

import React, { useState, useCallback } from 'react'

type AuthLayoutProps = {
  children: React.ReactNode
  /** Hide the logo (e.g. setup wizard manages its own header) */
  hideLogo?: boolean
  /** Extra className on the card container */
  cardClassName?: string
  /** Footer content rendered below the card inside the frosted panel */
  footer?: React.ReactNode
}

const AuthLayout: React.FC<AuthLayoutProps> = ({ children, hideLogo, cardClassName, footer }) => {
  const [mountKey] = useState(() => Date.now())
  const [effectsPaused, setEffectsPaused] = useState(false)

  const [animationData] = useState(() => {
    const blobSize = 50
    const waypoints = []
    for (let i = 0; i < 5; i++) {
      waypoints.push({
        x1: -blobSize / 2 + Math.random() * (100 + blobSize / 2),
        y1: -blobSize / 2 + Math.random() * (100 + blobSize / 2),
        x2: -blobSize / 2 + Math.random() * (100 + blobSize / 2),
        y2: -blobSize / 2 + Math.random() * (100 + blobSize / 2),
        s1: 1 + Math.random(), o1: 0.5 + Math.random() * 0.5,
        s2: 1 + Math.random(), o2: 0.5 + Math.random() * 0.5,
      })
    }
    const durations = waypoints.map(() => 20 + Math.random() * 20)
    const gradientDuration = 20 + Math.random() * 20
    const startAngle = Math.random() * 360
    const keyframes = `
      @keyframes gradient-rotate { 0% { transform: translate(-50%, -50%) rotate(${startAngle}deg); } 100% { transform: translate(-50%, -50%) rotate(${startAngle + 360}deg); } }
      @keyframes blob1 { 0%, 100% { left: ${waypoints[0].x1}%; top: ${waypoints[0].y1}%; } 50% { left: ${waypoints[2].x1}%; top: ${waypoints[2].y1}%; } }
      @keyframes blob2 { 0%, 100% { left: ${waypoints[0].x2}%; top: ${waypoints[0].y2}%; } 50% { left: ${waypoints[2].x2}%; top: ${waypoints[2].y2}%; } }
    `
    return { keyframes, durations, blobSize, gradientDuration }
  })

  const toggleEffects = useCallback(() => setEffectsPaused(p => !p), [])

  const animationStyle = effectsPaused ? 'paused' : 'running'

  return (
    <div key={mountKey} className="relative min-h-screen flex items-center justify-center overflow-hidden bg-gray-900">
      <style>{animationData.keyframes}</style>

      {/* Rotating conic gradient */}
      <div
        className="absolute rounded-full"
        style={{
          width: '200vmax', height: '200vmax', left: '50%', top: '50%',
          background: 'conic-gradient(from 0deg, #581c87, #1e3a8a, #581c87)',
          animation: `gradient-rotate ${animationData.gradientDuration}s linear infinite`,
          animationPlayState: animationStyle,
        }}
      />

      {/* Floating blobs */}
      <div className="absolute inset-0 overflow-hidden">
        <div
          className="absolute rounded-full bg-purple-900"
          style={{
            width: `${animationData.blobSize}vmin`, height: `${animationData.blobSize}vmin`,
            animation: `blob1 ${animationData.durations[0]}s infinite ease-in-out`,
            animationPlayState: animationStyle,
            filter: 'blur(5vmin)',
          }}
        />
        <div
          className="absolute rounded-full bg-blue-900"
          style={{
            width: `${animationData.blobSize}vmin`, height: `${animationData.blobSize}vmin`,
            animation: `blob2 ${animationData.durations[1]}s infinite ease-in-out`,
            animationPlayState: animationStyle,
            filter: 'blur(5vmin)',
          }}
        />
      </div>

      {/* Pause/play toggle */}
      <button
        onClick={toggleEffects}
        className="absolute bottom-4 right-4 z-20 text-white/30 hover:text-white/60 transition-colors text-xs flex items-center gap-1"
        title={effectsPaused ? 'Resume effects' : 'Pause effects'}
        aria-label={effectsPaused ? 'Resume background effects' : 'Pause background effects'}
      >
        {effectsPaused ? '▶' : '❚❚'}
      </button>

      {/* Card — overflow-hidden is on the inner div so focus rings on inputs aren't clipped */}
      <div className={`relative z-10 w-full max-w-md mx-4 rounded-2xl border border-white/30 shadow-[0_35px_60px_-15px_rgba(0,0,0,0.6)] ${cardClassName || ''}`}>
        <div className="bg-white/95 backdrop-blur-xl px-8 pt-8 pb-6 rounded-2xl overflow-hidden">
          {/* Logo */}
          {!hideLogo && (
            <div className="flex flex-col items-center mb-6">
              <img src="/logo_v.png" alt="Agience Logo" className="w-full h-auto max-w-[240px]" />
            </div>
          )}

          {children}

          {footer}
        </div>
      </div>
    </div>
  )
}

export default AuthLayout
