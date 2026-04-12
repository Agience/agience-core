/**
 * pages/SetupWizard.tsx
 *
 * First-boot setup wizard. Creates the platform operator account,
 * configures essential services, and completes platform setup.
 *
 * UX: Simple, welcoming, progressive. One action per step.
 * Reference: .dev/features/zero-config-bootstrap.md (Auth UX Guidelines)
 */

import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { toast } from 'sonner'
import AuthLayout from '../components/layout/AuthLayout'
import CreateAccountForm from '../components/auth/CreateAccountForm'
import {
  validateSetupToken,
  validateConnection,
  completeSetup,
  getSetupStatus,
  type SettingInput,
} from '../api/setup'

// ---------------------------------------------------------------------------
//  Types
// ---------------------------------------------------------------------------

type WizardStep = 'welcome' | 'domain' | 'auth' | 'operator' | 'email' | 'ai' | 'review'

interface StepAction {
  label: string
  onClick: () => void
  disabled?: boolean
  note?: string
}

// ---------------------------------------------------------------------------
//  Main Component
// ---------------------------------------------------------------------------

const SetupWizard: React.FC = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { setAuthData } = useAuth()

  // On localhost, skip domain and auth steps — platformUrl is already correct
  // and email/password is the right default for local dev.
  const isLocalhost = useMemo(() => ['localhost', '127.0.0.1'].includes(window.location.hostname), [])
  const STEPS: WizardStep[] = useMemo(
    () => isLocalhost
      ? ['welcome', 'operator', 'email', 'ai', 'review']
      : ['welcome', 'domain', 'auth', 'operator', 'email', 'ai', 'review'],
    [isLocalhost]
  )

  const [currentStep, setCurrentStep] = useState<WizardStep>('welcome')
  const [submitting, setSubmitting] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const restartPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Step 1: Welcome
  const [setupToken, setSetupToken] = useState('')
  const [tokenValid, setTokenValid] = useState(false)
  const [tokenAutoValidated, setTokenAutoValidated] = useState(false)
  const [autoValidating, setAutoValidating] = useState(false)

  // Step 2: Domain
  const [platformUrl, setPlatformUrl] = useState(() => {
    const { protocol, hostname, port } = window.location
    // home.agience.ai is always HTTPS in production — normalize regardless of dev access method
    if (hostname === 'home.agience.ai') return 'https://home.agience.ai'
    const defaultPort = protocol === 'https:' ? '443' : '80'
    return `${protocol}//${hostname}${port && port !== defaultPort ? `:${port}` : ''}`
  })

  // Step 3: Sign-In
  const [emailAuthEnabled, setEmailAuthEnabled] = useState(true)
  const [googleClientId, setGoogleClientId] = useState('')
  const [showGoogleSetup, setShowGoogleSetup] = useState(false)

  // Step 4: Operator account
  const [opEmail, setOpEmail] = useState('')
  const [opPassword, setOpPassword] = useState('')
  const [opName, setOpName] = useState('')

  // Step 5: Email service
  const [emailProvider, setEmailProvider] = useState('')
  const [emailConfig, setEmailConfig] = useState<Record<string, string>>({})

  // Step 6: AI
  const [aiProvider, setAiProvider] = useState<'relay' | 'openrouter' | 'openai' | null>(null)
  const [openrouterKey, setOpenrouterKey] = useState('')
  const [openaiKey, setOpenaiKey] = useState('')
  const [openaiKeyFromEnv, setOpenaiKeyFromEnv] = useState(false)

  // Connection test results
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; error?: string }>>({})

  const stepIndex = STEPS.indexOf(currentStep)

  const goNext = useCallback(() => {
    const idx = STEPS.indexOf(currentStep)
    if (idx < STEPS.length - 1) setCurrentStep(STEPS[idx + 1])
  }, [STEPS, currentStep])

  const goBack = useCallback(() => {
    const idx = STEPS.indexOf(currentStep)
    if (idx > 0) setCurrentStep(STEPS[idx - 1])
  }, [STEPS, currentStep])

  // -- Handlers --

  const handleValidateToken = async () => {
    setSubmitting(true)
    try {
      const valid = await validateSetupToken(setupToken)
      if (valid) {
        setTokenValid(true)
        goNext()
      } else {
        toast.error('Invalid setup token. Check your terminal output.')
      }
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 410) {
        toast.error('Setup is already complete.', {
          action: { label: 'Sign in', onClick: () => navigate('/login') },
        })
      } else {
        toast.error('Could not validate token. Is the backend running?')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleTestConnection = async (service: string, config: Record<string, unknown>) => {
    setTestResults(prev => ({ ...prev, [service]: { success: false } }))
    try {
      const result = await validateConnection(setupToken, service, config)
      setTestResults(prev => ({ ...prev, [service]: { success: result.success, error: result.error ?? undefined } }))
      if (result.success) {
        toast.success(`${service} connection successful`)
      } else {
        toast.error(result.error || `${service} connection failed`)
      }
    } catch {
      setTestResults(prev => ({ ...prev, [service]: { success: false, error: 'Connection test failed' } }))
      toast.error(`${service} connection test failed`)
    }
  }

  const handleComplete = async () => {
    setSubmitting(true)
    try {
      // Google-only: no operator record created during setup.
      // The first person to sign in with Google will be promoted to operator.
      const operator = googleOnly ? null : {
        ...(opEmail ? { email: opEmail } : {}),
        ...(emailAuthEnabled && opPassword ? { password: opPassword } : {}),
        ...(opName ? { name: opName } : {}),
      }

      const settings: SettingInput[] = []

      // Platform URL
      if (platformUrl) {
        settings.push({ key: 'platform.base_url', value: platformUrl, category: 'platform' })
      }

      // Auth methods
      settings.push({ key: 'auth.email.enabled', value: emailAuthEnabled ? 'true' : 'false', category: 'auth' })
      if (googleClientId) {
        settings.push({ key: 'auth.google.client_id', value: googleClientId, category: 'auth' })
      }

      // AI (optional)
      if (aiProvider === 'relay') {
        settings.push({ key: 'ai.provider', value: 'relay', category: 'ai' })
      } else if (aiProvider === 'openrouter' && openrouterKey) {
        settings.push({ key: 'ai.provider', value: 'openrouter', category: 'ai' })
        settings.push({ key: 'ai.openrouter_api_key', value: openrouterKey, category: 'ai', is_secret: true })
      } else if (aiProvider === 'openai' && (openaiKey || openaiKeyFromEnv)) {
        settings.push({ key: 'ai.provider', value: 'openai', category: 'ai' })
        if (openaiKey && !openaiKeyFromEnv) {
          settings.push({ key: 'ai.openai_api_key', value: openaiKey, category: 'ai', is_secret: true })
        }
      }

      // Email
      if (emailProvider) {
        settings.push({ key: 'email.provider', value: emailProvider, category: 'email' })
        // Provider-specific keys (host, port, username, password, api_key, etc.)
        // from_address and from_name are provider-agnostic — handled below.
        for (const [k, v] of Object.entries(emailConfig)) {
          if (v && k !== 'from_address' && k !== 'from_name') {
            const isSecret = k.includes('password') || k.includes('secret') || k.includes('api_key')
            settings.push({ key: `email.${emailProvider}.${k}`, value: v, category: 'email', is_secret: isSecret })
          }
        }
        // Provider-agnostic sender identity — stored at top-level email.* keys
        if (emailConfig.from_address) {
          settings.push({ key: 'email.from_address', value: emailConfig.from_address, category: 'email' })
        }
        if (emailConfig.from_name) {
          settings.push({ key: 'email.from_name', value: emailConfig.from_name, category: 'email' })
        }
      }

      const result = await completeSetup(setupToken, operator, settings)

      // Hold the token until the backend finishes restarting — calling
      // setAuthData now would trigger /auth/userinfo which returns 503.
      const pendingToken = result.access_token || null
      setRestarting(true)

      restartPollRef.current = setInterval(async () => {
        try {
          const status = await getSetupStatus()
          if (status.ready) {
            if (restartPollRef.current) clearInterval(restartPollRef.current)
            // Store the token now that the backend is ready and will accept it.
            if (pendingToken) {
              setAuthData(pendingToken)
            }
            // Tell SetupGate setup is done — it will flip to needsSetup=false
            // without re-fetching, eliminating the spinner flash.
            window.dispatchEvent(new Event('setup-complete'))
            // Google-only: navigate to login with the setup token so the backend
            // can verify and promote the first sign-in to platform operator.
            const target = (!emailAuthEnabled && showGoogleSetup) ? `/login?setup_token=${encodeURIComponent(setupToken)}` : '/'
            navigate(target, { replace: true })
          }
        } catch {
          // backend still restarting — keep polling
        }
      }, 2000)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const msg = detail || (err instanceof Error ? err.message : 'Setup failed')
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  // Clean up polling interval on unmount
  useEffect(() => {
    return () => {
      if (restartPollRef.current) clearInterval(restartPollRef.current)
    }
  }, [])

  // Auto-validate token from ?token= query param (e.g. from the setup URL in logs)
  useEffect(() => {
    const urlToken = searchParams.get('token')
    if (!urlToken || tokenValid) return
    setSetupToken(urlToken)
    setAutoValidating(true)
    // Strip the token from the URL immediately so it doesn't linger
    window.history.replaceState(null, '', '/setup')
    validateSetupToken(urlToken)
      .then(valid => {
        if (valid) {
          setTokenValid(true)
          setTokenAutoValidated(true)
        } else {
          toast.error('Setup link has expired or is invalid. Enter the token manually.')
        }
      })
      .catch(err => {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 410) {
          toast.error('Setup is already complete.', {
            action: { label: 'Sign in', onClick: () => navigate('/login') },
          })
        } else {
          toast.error('Could not validate setup token. Is the backend running?')
        }
      })
      .finally(() => setAutoValidating(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Pre-configure AI step if the operator set OPENAI_API_KEY in .env
  useEffect(() => {
    getSetupStatus()
      .then(status => {
        if (status.env_defaults?.openai_api_key) {
          setAiProvider('openai')
          setOpenaiKeyFromEnv(true)
        }
      })
      .catch(() => {/* setup status fetch failed — non-fatal */})
  }, [])

  // Compute primary action button config for current step — drives the pinned Continue button
  const stepAction: StepAction | null = (() => {
    switch (currentStep) {
      case 'welcome':
        if (autoValidating) return null
        if (tokenAutoValidated) return { label: 'Get started', onClick: goNext }
        return { label: submitting ? 'Validating…' : 'Continue', onClick: handleValidateToken, disabled: !setupToken || submitting }
      case 'domain':
        return { label: 'Continue', onClick: goNext }
      case 'auth':
        return {
          label: 'Continue',
          onClick: goNext,
          disabled: !emailAuthEnabled && !(showGoogleSetup && (platformUrl === 'https://home.agience.ai' || !!googleClientId)),
        }
      case 'operator':
        if (!emailAuthEnabled && showGoogleSetup) return { label: 'Continue', onClick: goNext }
        return null // CreateAccountForm renders its own submit button
      case 'email':
        return {
          label: emailProvider ? 'Continue' : 'Skip for now',
          onClick: goNext,
          note: !emailProvider ? 'Without email, users can only sign in with a password. No password reset or login codes.' : undefined,
        }
      case 'ai':
        return {
          label: aiProvider ? 'Continue' : 'Skip for now',
          onClick: goNext,
          note: !aiProvider ? "Without AI, search and embeddings won't work. You can configure it later in settings." : undefined,
        }
      case 'review':
        return { label: submitting ? 'Setting up…' : 'Complete Setup', onClick: handleComplete, disabled: submitting }
      default:
        return null
    }
  })()

  // ---------------------------------------------------------------------------
  //  Step Renderers
  // ---------------------------------------------------------------------------

  const renderWelcome = () => {
    if (autoValidating) {
      return (
        <div className="space-y-6 text-center">
          <p className="text-gray-500">Verifying setup link…</p>
        </div>
      )
    }
    if (tokenAutoValidated) {
      return (
        <div className="space-y-6">
          <div className="text-center space-y-2">
            <p className="text-2xl font-semibold text-gray-900">Welcome</p>
            <p className="text-gray-500">Let's get you set up. This takes about 2 minutes.</p>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
            ✓ Setup token verified
          </div>
        </div>
      )
    }
    return (
      <div className="space-y-6">
        <div className="text-center space-y-2">          
          <p className="text-2xl font-semibold text-gray-900">Welcome</p>
          <p className="text-gray-500">Let's get you set up. This takes about 2 minutes.</p>
        </div>
        <div className="space-y-2">          
          <input
            id="setup-token"
            type="text"
            value={setupToken}
            onChange={e => setSetupToken(e.target.value)}
            placeholder="Paste the token from your terminal"
            className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent text-sm"
            autoFocus
            autoComplete="off"
          />
          <p className="text-xs text-gray-400">
            Admins can find the setup URL in backend startup logs or run{' '}
            <code className="bg-gray-100 px-1 py-0.5 rounded text-xs">docker logs agience-backend</code>
          </p>
        </div>
      </div>
    )
  }

  const renderDomain = () => (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold text-gray-900">Platform URL</h1>
        <p className="text-gray-500">The address where this instance is hosted.</p>
      </div>
      {platformUrl === 'https://home.agience.ai' && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-xs text-green-800">
          <p className="font-medium">✓ home.agience.ai detected</p>
          <p className="mt-0.5 text-green-700">HTTPS and Google Sign-In are pre-configured for the best local experience.</p>
        </div>
      )}
      <div className="space-y-1.5">
        <input
          type="text"
          value={platformUrl}
          onChange={e => setPlatformUrl(e.target.value)}
          onBlur={e => setPlatformUrl(e.target.value.replace(/\/+$/, ''))}
          className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm font-mono"
          placeholder="https://home.agience.ai"
        />
        <p className="text-xs text-gray-400">Auto-detected. Use <span className="font-mono">https://home.agience.ai</span> for the best local experience, or enter your custom domain.</p>
      </div>
    </div>
  )

  const renderAuth = () => {
    const isHomeAgience = platformUrl === 'https://home.agience.ai'
    const redirectUri = `${platformUrl}/api/auth/callback`
    return (
      <div className="space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-semibold text-gray-900">Sign-In</h1>
          <p className="text-gray-500">Choose how users will log in to this instance.</p>
        </div>

        {/* Email/password */}
        {!emailAuthEnabled ? (
          <button
            onClick={() => setEmailAuthEnabled(true)}
            className="w-full text-left px-4 py-3 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors text-sm text-gray-700"
          >
            <span className="font-medium">+ Add Email &amp; password</span>
            <span className="text-xs text-gray-400 ml-2">— Users sign in with their email address.</span>
          </button>
        ) : (
          <div className="flex items-center justify-between px-4 py-3 rounded-lg border border-green-200 bg-green-50 text-sm">
            <div>
              <span className="font-medium text-gray-800">✓ Email &amp; password</span>
              <span className="text-xs text-gray-400 ml-2">— Users sign in with their email address.</span>
            </div>
            <button onClick={() => setEmailAuthEnabled(false)} className="text-xs text-gray-400 hover:text-gray-600 ml-4 shrink-0">Remove</button>
          </div>
        )}

        {/* Google (optional) */}
        {!showGoogleSetup ? (
          <button
            onClick={() => setShowGoogleSetup(true)}
            className="w-full text-left px-4 py-3 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors text-sm text-gray-700"
          >
            <span className="font-medium">+ Add Google Sign-In</span>
            {isHomeAgience
              ? <span className="text-xs text-green-600 ml-2">— Zero config on home.agience.ai ✓</span>
              : <span className="text-xs text-gray-400 ml-2">— Requires a Google Cloud OAuth app.</span>
            }
          </button>
        ) : isHomeAgience ? (
          <div className="flex items-center justify-between px-4 py-3 rounded-lg border border-green-200 bg-green-50 text-sm">
            <div>
              <span className="font-medium text-gray-800">✓ Google Sign-In</span>
              <span className="text-xs text-gray-400 ml-2">— Pre-configured for home.agience.ai.</span>
            </div>
            <button onClick={() => { setShowGoogleSetup(false); setGoogleClientId('') }} className="text-xs text-gray-400 hover:text-gray-600 ml-4 shrink-0">Remove</button>
          </div>
        ) : (
          <div className="space-y-3 px-4 py-4 rounded-lg border border-indigo-200 bg-indigo-50">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-indigo-900">✓ Google Sign-In</p>
              <button onClick={() => { setShowGoogleSetup(false); setGoogleClientId('') }} className="text-xs text-gray-400 hover:text-gray-600">Remove</button>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-2.5 space-y-1.5 text-xs">
              <p className="font-medium text-gray-700">Add this redirect URI to your Google OAuth credentials</p>
              <p className="font-mono text-gray-600 break-all select-all bg-gray-50 rounded px-2 py-1">{redirectUri}</p>
              <p className="text-gray-500">
                <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">console.cloud.google.com</a>
                {' '}→ OAuth 2.0 Client IDs → Authorised redirect URIs
              </p>
            </div>
            <input
              type="text"
              value={googleClientId}
              onChange={e => setGoogleClientId(e.target.value.trim())}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 text-xs font-mono bg-white"
              placeholder="xxxxxxxxxxxx-xxxxxxxx.apps.googleusercontent.com"
              autoFocus
            />
          </div>
        )}

      </div>
    )
  }

  const googleOnly = !emailAuthEnabled && showGoogleSetup

  const renderOperator = () => {
    if (googleOnly) {
      return (
        <div className="space-y-6">
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-semibold text-gray-900">Operator access</h1>
            <p className="text-gray-500">You chose Google Sign-In, so no account setup is needed here.</p>
          </div>
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-4 text-sm text-indigo-900 space-y-1">
            <p className="font-medium">Sign in with Google after setup completes.</p>
            <p className="text-indigo-700 text-xs">The first person to sign in with Google will automatically become the platform operator.</p>
          </div>
        </div>
      )
    }
    return (
      <CreateAccountForm
        email={opEmail}
        onEmailChange={setOpEmail}
        name={opName}
        onNameChange={setOpName}
        password={opPassword}
        onPasswordChange={setOpPassword}
        requirePassword={emailAuthEnabled}
        onSubmit={goNext}
        submitLabel="Continue"
      />
    )
  }

  const renderEmailService = () => (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold text-gray-900">Email service</h1>
        <p className="text-gray-500">Enables login codes, password reset, and invitations.</p>
      </div>
      <div className="space-y-3">
        {/* Agience relay — recommended */}
        <button
          onClick={() => { setEmailProvider('relay'); setEmailConfig({}) }}
          className={`w-full text-left px-4 py-3 rounded-lg border transition-colors text-sm ${
            emailProvider === 'relay'
              ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
              : 'border-gray-200 hover:border-gray-300 text-gray-700'
          }`}
        >
          <span className="font-medium">Agience relay</span>
          <span className="ml-2 text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded font-medium">Recommended</span>
          <span className="text-xs text-gray-400 ml-2">— Zero config, free up to 100/day</span>
        </button>

        {/* Relay opt-in notice */}
        {emailProvider === 'relay' && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-xs text-gray-600 space-y-1">
            <p>Agience sends login codes and password resets via <strong>relay.agience.ai</strong>. Addresses are used to deliver each message only — not stored or shared.</p>
            <p>Free tier: <strong>10 emails/day</strong> — enough to verify your setup. Upgrade plans available in settings.</p>
            <p><a href="https://agience.ai/privacy" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">Privacy policy →</a></p>
          </div>
        )}

        {/* Divider */}
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <div className="flex-1 border-t border-gray-200" />
          <span>or bring your own</span>
          <div className="flex-1 border-t border-gray-200" />
        </div>

        {(['smtp', 'ses', 'sendgrid', 'resend'] as const).map(provider => (
          <button
            key={provider}
            onClick={() => {
              setEmailProvider(provider)
              setEmailConfig({})
            }}
            className={`w-full text-left px-4 py-3 rounded-lg border transition-colors text-sm ${
              emailProvider === provider
                ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
                : 'border-gray-200 hover:border-gray-300 text-gray-700'
            }`}
          >
            <span className="font-medium capitalize">{provider === 'ses' ? 'AWS SES' : provider === 'smtp' ? 'SMTP' : provider.charAt(0).toUpperCase() + provider.slice(1)}</span>
            <span className="text-xs text-gray-400 ml-2">
              {provider === 'smtp' && '— Any provider (Gmail, Mailgun, etc.)'}
              {provider === 'ses' && '— Amazon Simple Email Service'}
              {provider === 'sendgrid' && '— SendGrid API'}
              {provider === 'resend' && '— Resend API'}
            </span>
          </button>
        ))}

        {/* SMTP config */}
        {emailProvider === 'smtp' && (
          <div className="space-y-3 pt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label htmlFor="smtp-host" className="block text-xs font-medium text-gray-600">Host</label>
                <input id="smtp-host" type="text" value={emailConfig.host || ''} onChange={e => setEmailConfig(p => ({ ...p, host: e.target.value }))} placeholder="smtp.gmail.com" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="smtp-port" className="block text-xs font-medium text-gray-600">Port</label>
                <input id="smtp-port" type="text" value={emailConfig.port || ''} onChange={e => setEmailConfig(p => ({ ...p, port: e.target.value }))} placeholder="587" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
              </div>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="smtp-username" className="block text-xs font-medium text-gray-600">Username</label>
              <input id="smtp-username" type="text" value={emailConfig.username || ''} onChange={e => setEmailConfig(p => ({ ...p, username: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="smtp-password" className="block text-xs font-medium text-gray-600">Password</label>
              <input id="smtp-password" type="password" value={emailConfig.password || ''} onChange={e => setEmailConfig(p => ({ ...p, password: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="smtp-from-address" className="block text-xs font-medium text-gray-600">From address</label>
              <input id="smtp-from-address" type="email" value={emailConfig.from_address || ''} onChange={e => setEmailConfig(p => ({ ...p, from_address: e.target.value }))} placeholder="noreply@yourdomain.com" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <button
              onClick={() => handleTestConnection('smtp', emailConfig)}
              className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
            >
              {testResults.smtp?.success ? '✓ Connected' : 'Test connection →'}
            </button>
          </div>
        )}

        {/* API key providers (SendGrid, Resend) */}
        {(emailProvider === 'sendgrid' || emailProvider === 'resend') && (
          <div className="space-y-3 pt-2">
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600">API key</label>
              <input type="password" value={emailConfig.api_key || ''} onChange={e => setEmailConfig(p => ({ ...p, api_key: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600">From address</label>
              <input type="email" value={emailConfig.from_address || ''} onChange={e => setEmailConfig(p => ({ ...p, from_address: e.target.value }))} placeholder="noreply@yourdomain.com" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <button
              onClick={() => handleTestConnection(emailProvider, emailConfig)}
              className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
            >
              {testResults[emailProvider]?.success ? '✓ Connected' : 'Test connection →'}
            </button>
          </div>
        )}

        {/* SES */}
        {emailProvider === 'ses' && (
          <div className="space-y-3 pt-2">
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600">Region</label>
              <input type="text" value={emailConfig.region || ''} onChange={e => setEmailConfig(p => ({ ...p, region: e.target.value }))} placeholder="us-east-1" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600">Access key ID</label>
              <input type="text" value={emailConfig.access_key_id || ''} onChange={e => setEmailConfig(p => ({ ...p, access_key_id: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600">Secret access key</label>
              <input type="password" value={emailConfig.secret_access_key || ''} onChange={e => setEmailConfig(p => ({ ...p, secret_access_key: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600">From address</label>
              <input type="email" value={emailConfig.from_address || ''} onChange={e => setEmailConfig(p => ({ ...p, from_address: e.target.value }))} placeholder="noreply@yourdomain.com" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <button
              onClick={() => handleTestConnection('ses', emailConfig)}
              className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
            >
              {testResults.ses?.success ? '✓ Connected' : 'Test connection →'}
            </button>
          </div>
        )}
      </div>
    </div>
  )

  const renderAI = () => (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold text-gray-900">AI Access</h1>
        <p className="text-gray-500">Powers search, embeddings, and AI features.</p>
      </div>
      <div className="space-y-3">
        {/* Agience relay — recommended */}
        <button
          onClick={() => { setAiProvider('relay'); setOpenaiKey(''); setOpenrouterKey(''); setOpenaiKeyFromEnv(false) }}
          className={`w-full text-left px-4 py-3 rounded-lg border transition-colors text-sm ${
            aiProvider === 'relay'
              ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
              : 'border-gray-200 hover:border-gray-300 text-gray-700'
          }`}
        >
          <span className="font-medium">Agience AI</span>
          <span className="ml-2 text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded font-medium">Recommended</span>
          <span className="text-xs text-gray-400 ml-2">— Zero config, free up to 50 queries/day</span>
        </button>

        {/* Relay notice */}
        {aiProvider === 'relay' && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-xs text-gray-600 space-y-1">
            <p>Queries are routed through <strong>relay.agience.ai</strong> using Agience's model access. Prompts are not logged or used for training.</p>
            <p>Free tier: <strong>50 queries/day</strong> — enough to verify your setup. Bring your own key or upgrade in settings for full access.</p>
            <p><a href="https://agience.ai/privacy" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">Privacy policy →</a></p>
          </div>
        )}

        {/* Divider */}
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <div className="flex-1 border-t border-gray-200" />
          <span>or bring your own</span>
          <div className="flex-1 border-t border-gray-200" />
        </div>

        {/* OpenRouter */}
        <button
          onClick={() => { setAiProvider('openrouter'); setOpenaiKey(''); setOpenaiKeyFromEnv(false) }}
          className={`w-full text-left px-4 py-3 rounded-lg border transition-colors text-sm ${
            aiProvider === 'openrouter'
              ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
              : 'border-gray-200 hover:border-gray-300 text-gray-700'
          }`}
        >
          <span className="font-medium">OpenRouter</span>
          <span className="text-xs text-gray-400 ml-2">— Any model, free tier available</span>
        </button>

        {aiProvider === 'openrouter' && (
          <div className="space-y-2">
            <input
              type="password"
              value={openrouterKey}
              onChange={e => setOpenrouterKey(e.target.value)}
              placeholder="sk-or-..."
              className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm font-mono"
              autoComplete="off"
              autoFocus
            />
            <p className="text-xs text-gray-400">
              Get a free key at <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">openrouter.ai/keys</a>
            </p>
          </div>
        )}

        {/* OpenAI direct */}
        <button
          onClick={() => { setAiProvider('openai'); setOpenrouterKey('') }}
          className={`w-full text-left px-4 py-3 rounded-lg border transition-colors text-sm ${
            aiProvider === 'openai'
              ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
              : 'border-gray-200 hover:border-gray-300 text-gray-700'
          }`}
        >
          <span className="font-medium">OpenAI</span>
          <span className="text-xs text-gray-400 ml-2">— Direct API key</span>
        </button>

        {aiProvider === 'openai' && (
          openaiKeyFromEnv ? (
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-xs text-green-700">
              <p>✓ API key detected from environment configuration.</p>
            </div>
          ) : (
          <div className="space-y-2">
            <input
              id="openai-key"
              type="password"
              value={openaiKey}
              onChange={e => setOpenaiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm font-mono"
              autoComplete="off"
              autoFocus
            />
            {openaiKey && (
              <button
                onClick={() => handleTestConnection('openai', { api_key: openaiKey })}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
              >
                {testResults.openai?.success ? '✓ Valid' : 'Test key →'}
              </button>
            )}
          </div>
          )
        )}
      </div>

    </div>
  )

  const renderReview = () => (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold text-gray-900">Ready to go</h1>
        <p className="text-gray-500">Review your settings and complete setup.</p>
      </div>
      <div className="space-y-3 text-sm">
        {!isLocalhost && (
          <div className="flex justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">URL</span>
            <span className="text-gray-900 font-medium font-mono text-xs">{platformUrl}</span>
          </div>
        )}
        <div className="flex justify-between py-2 border-b border-gray-100">
          <span className="text-gray-500">Username</span>
          <span className="text-gray-900 font-medium">{googleOnly ? 'First Google sign-in' : (opName || opEmail || '—')}</span>
        </div>
        <div className="flex justify-between py-2 border-b border-gray-100">
          <span className="text-gray-500">Email service</span>
          <span className="text-gray-900 font-medium">{emailProvider ? emailProvider.toUpperCase() : 'Not configured'}</span>
        </div>
        <div className="flex justify-between py-2 border-b border-gray-100">
          <span className="text-gray-500">AI</span>
          <span className="text-gray-900 font-medium">{
            aiProvider === 'relay' ? 'Agience relay' :
            aiProvider === 'openrouter' ? 'OpenRouter' :
            aiProvider === 'openai' ? (openaiKeyFromEnv ? 'OpenAI (from environment)' : 'OpenAI') :
            'Not configured'
          }</span>
        </div>
        <div className="flex justify-between py-2 border-b border-gray-100">
          <span className="text-gray-500">Sign-In</span>
          <span className="text-gray-900 font-medium">
            {[emailAuthEnabled && 'Password', googleClientId && 'Google'].filter(Boolean).join(' + ') || 'None'}
          </span>
        </div>
      </div>
    </div>
  )

  const renderStep = () => {
    switch (currentStep) {
      case 'welcome': return renderWelcome()
      case 'domain': return renderDomain()
      case 'auth': return renderAuth()
      case 'operator': return renderOperator()
      case 'email': return renderEmailService()
      case 'ai': return renderAI()
      case 'review': return renderReview()
    }
  }

  // ---------------------------------------------------------------------------
  //  Layout — uses shared AuthLayout (logo, animated background, glass card)
  // ---------------------------------------------------------------------------

  if (restarting) {
    return (
      <AuthLayout>
        <div className="text-center space-y-4">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 mb-2">
            <svg className="animate-spin h-8 w-8 text-gray-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
          <h2 className="text-2xl font-semibold text-gray-900">Setup complete!</h2>
          <p className="text-gray-500 text-sm max-w-xs mx-auto">
            The platform is initialising. This takes a few seconds…
          </p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      {/* Progress dots */}
      <div className="flex justify-center gap-2 mb-4">
        {STEPS.map((step, i) => (
          <div
            key={step}
            className={`w-2 h-2 rounded-full transition-colors ${
              i <= stepIndex ? 'bg-gray-900' : 'bg-gray-200'
            }`}
          />
        ))}
      </div>

      {/* Back button — fixed height prevents layout shift when it appears/disappears */}
      <div className="h-7 mb-3">
        {stepIndex > 0 && (
          <button
            onClick={goBack}
            className="text-sm text-gray-400 hover:text-gray-600 flex items-center gap-1"
          >
            ← Back
          </button>
        )}
      </div>

      {/* Fixed-height area: content scrolls if too tall, action button always pinned at bottom */}
      <div className="flex flex-col h-[400px]">
        <div className="flex-1 min-h-0 overflow-y-auto px-1 -mx-1 py-1 -my-1">
          {renderStep()}
        </div>
        {stepAction && (
          <div className="shrink-0 pt-4 border-t border-gray-100 mt-4">
            <button
              onClick={stepAction.onClick}
              disabled={stepAction.disabled}
              className="w-full py-2.5 bg-gray-900 text-white rounded-lg font-medium hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
            >
              {stepAction.label}
            </button>
            {stepAction.note && (
              <p className="text-xs text-gray-400 text-center mt-2">{stepAction.note}</p>
            )}
          </div>
        )}
      </div>
    </AuthLayout>
  )
}

export default SetupWizard
