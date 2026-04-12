/**
 * api/setup.ts
 *
 * Setup wizard and operator settings API client.
 */

import { get, post } from './api'

// ---------------------------------------------------------------------------
//  Setup wizard (unauthenticated, only available during setup mode)
// ---------------------------------------------------------------------------

export type SetupStatus = {
  needs_setup: boolean
  ready: boolean
  version: string
  env_defaults?: Record<string, boolean>
}

export type ValidateConnectionResult = {
  success: boolean
  error: string | null
}

export type OperatorAccount = {
  email?: string
  password?: string
  name?: string
  passkey_credential?: Record<string, unknown>
  passkey_challenge?: string
  passkey_device_name?: string
}

export type SettingInput = {
  key: string
  value: string
  category: string
  is_secret?: boolean
}

export type SetupCompleteResult = {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function getSetupStatus(): Promise<SetupStatus> {
  return get<SetupStatus>('/setup/status')
}

export async function validateSetupToken(token: string): Promise<boolean> {
  const res = await post<{ valid: boolean }>('/setup/validate-token', { token })
  return res.valid
}

export async function validateConnection(
  setupToken: string,
  service: string,
  config: Record<string, unknown>
): Promise<ValidateConnectionResult> {
  return post<ValidateConnectionResult>(
    '/setup/validate-connection',
    { service, config },
    { headers: { 'X-Setup-Token': setupToken } }
  )
}

export async function completeSetup(
  setupToken: string,
  operator: OperatorAccount | null,
  settings: SettingInput[]
): Promise<SetupCompleteResult> {
  return post<SetupCompleteResult>(
    '/setup/complete',
    { operator, settings },
    { headers: { 'X-Setup-Token': setupToken } }
  )
}

// ---------------------------------------------------------------------------
//  Passkey auth
// ---------------------------------------------------------------------------

export type PasskeyLoginOptions = {
  options: Record<string, unknown> | null
  has_passkeys: boolean
}

export async function getPasskeyLoginOptions(email: string): Promise<PasskeyLoginOptions> {
  return post<PasskeyLoginOptions>('/auth/passkey/login-options', { email })
}

export async function completePasskeyLogin(
  credential: Record<string, unknown>,
  challenge: string,
  userId: string
): Promise<{ access_token: string; refresh_token: string }> {
  return post('/auth/passkey/login-complete', {
    credential,
    challenge,
    user_id: userId,
  })
}

export async function getPasskeyRegisterOptions(): Promise<{ options: Record<string, unknown> }> {
  return post('/auth/passkey/register-options', {})
}

export async function completePasskeyRegistration(
  credential: Record<string, unknown>,
  challenge: string,
  deviceName?: string
): Promise<{ credential_id: string }> {
  return post('/auth/passkey/register-complete', {
    credential,
    challenge,
    device_name: deviceName,
  })
}

// ---------------------------------------------------------------------------
//  OTP auth
// ---------------------------------------------------------------------------

export async function requestOTP(email: string): Promise<{ sent: boolean }> {
  return post('/auth/otp/request', { email })
}

export async function verifyOTP(
  email: string,
  code: string
): Promise<{ access_token: string; refresh_token: string }> {
  return post('/auth/otp/verify', { email, code })
}

// Platform settings API moved to `api/platform.ts` (2026-04-06) when the
// operator_router was merged into platform_router. Use
// `getPlatformSettings` / `updatePlatformSettings` from there.
