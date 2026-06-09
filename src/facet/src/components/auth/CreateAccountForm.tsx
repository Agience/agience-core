/**
 * components/auth/CreateAccountForm.tsx
 *
 * Shared create-account form used by both the Login register phase
 * and the SetupWizard operator step.
 *
 * Owns: show/hide password toggle, password generator, copy feedback.
 * Caller owns: all field values + handlers, submit logic, footer slot.
 */

import React, { useState, useCallback } from 'react'

export type CreateAccountFormProps = {
  /** Primary identifier (username or email) shown as a read-only pill */
  identifier?: string
  /** Called when user clicks "Change" on the identifier pill */
  onChangeIdentifier?: () => void

  /** Optional email field — not required, suggested for recovery */
  email?: string
  onEmailChange?: (v: string) => void

  name: string
  onNameChange: (v: string) => void

  password: string
  onPasswordChange: (v: string) => void
  /** When false, hides the password field (e.g. Google-only auth) */
  requirePassword?: boolean

  submitting?: boolean
  onSubmit: () => void
  submitLabel?: string
  /** Extra content rendered below the submit button (links, disclaimers, etc.) */
  footer?: React.ReactNode
}

const CreateAccountForm: React.FC<CreateAccountFormProps> = ({
  identifier,
  onChangeIdentifier,
  email = '',
  onEmailChange,
  name,
  onNameChange,
  password,
  onPasswordChange,
  requirePassword = true,
  submitting = false,
  onSubmit,
  submitLabel = 'Create account',
  footer,
}) => {
  const [showPassword, setShowPassword] = useState(false)
  const [passwordCopied, setPasswordCopied] = useState(false)

  const passwordValid = password.length >= 12

  const generatePassword = useCallback(async () => {
    const upper   = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    const lower   = 'abcdefghijklmnopqrstuvwxyz'
    const digits  = '0123456789'
    const special = '!@#$%^&*-_=+.'
    const all = upper + lower + digits + special
    const length = 20
    const pick = (charset: string) => {
      const buf = new Uint32Array(1)
      crypto.getRandomValues(buf)
      return charset[buf[0] % charset.length]
    }
    const chars: string[] = [pick(upper), pick(lower), pick(digits), pick(special)]
    for (let i = chars.length; i < length; i++) chars.push(pick(all))
    for (let i = chars.length - 1; i > 0; i--) {
      const buf = new Uint32Array(1)
      crypto.getRandomValues(buf)
      const j = buf[0] % (i + 1)
      ;[chars[i], chars[j]] = [chars[j], chars[i]]
    }
    const pwd = chars.join('')
    onPasswordChange(pwd)
    setShowPassword(true)
    try {
      await navigator.clipboard.writeText(pwd)
      setPasswordCopied(true)
      setTimeout(() => setPasswordCopied(false), 2500)
    } catch { /* clipboard unavailable */ }
  }, [onPasswordChange])

  return (
    <form
      onSubmit={e => { e.preventDefault(); onSubmit() }}
      className="space-y-4"
    >
      {/* Identifier pill (read-only) — shown when coming from the login identifier phase */}
      {identifier && (
        <div className="flex items-center gap-2 text-sm text-gray-600 bg-gray-50 px-3 py-2 rounded-lg">
          <span>{identifier}</span>
          {onChangeIdentifier && (
            <button
              type="button"
              onClick={onChangeIdentifier}
              className="text-indigo-500 hover:underline text-xs ml-auto"
            >
              Change
            </button>
          )}
        </div>
      )}

      {/* Username / display name */}
      <div className="space-y-1.5">
        <label htmlFor="ca-name" className="block text-sm font-medium text-gray-700">Username</label>
        <input
          id="ca-name"
          type="text"
          value={name}
          onChange={e => onNameChange(e.target.value)}
          placeholder="Choose a username"
          className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent text-sm"
          autoFocus={!identifier}
          autoComplete="username"
          disabled={submitting}
        />
      </div>

      {/* Email — optional, for recovery */}
      <div className="space-y-1.5">
        <label htmlFor="ca-email" className="block text-sm font-medium text-gray-700 flex items-center gap-1.5">
          Email <span className="text-gray-400 font-normal text-xs">(optional)</span>
        </label>
        <input
          id="ca-email"
          type="email"
          value={email}
          onChange={e => onEmailChange?.(e.target.value)}
          placeholder="you@example.com"
          className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent text-sm"
          autoComplete="email"
          disabled={submitting}
        />
      </div>

      {/* Password */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label htmlFor="ca-password" className="block text-sm font-medium text-gray-700">Password</label>
          <button
            type="button"
            onClick={generatePassword}
            className="text-xs text-indigo-500 hover:text-indigo-700 transition-colors"
          >
            Generate strong password
          </button>
        </div>
        <div className="relative">
          <input
            id="ca-password"
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={e => onPasswordChange(e.target.value)}
            placeholder="Choose a strong password"
            className="w-full px-3 py-2.5 pr-10 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent text-sm"
            autoComplete="new-password"
            disabled={submitting}
          />
          <button
            type="button"
            onClick={() => setShowPassword(v => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            tabIndex={-1}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? '🙈' : '👁️'}
          </button>
        </div>
        {password && (
          <div className="flex items-center justify-between text-xs mt-1">
            <span className={passwordValid ? 'text-green-600' : 'text-gray-400'}>
              {passwordValid ? '✓' : '○'} At least 12 characters
            </span>
            {passwordCopied && <span className="text-green-600">Copied to clipboard ✓</span>}
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={submitting || !name || (requirePassword && (!password || !passwordValid))}
        // name = username field; email is optional
        className="w-full py-2.5 bg-gray-900 text-white rounded-lg font-medium hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
      >
        {submitting ? 'Creating account…' : submitLabel}
      </button>

      {footer}
    </form>
  )
}

export default CreateAccountForm
