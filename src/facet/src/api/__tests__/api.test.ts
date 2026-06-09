import { describe, it, expect, vi, afterEach } from 'vitest';

vi.mock('../../config/runtime', () => ({
	getRuntimeConfig: () => ({
		mantleUri: 'https://api.example.com',
		originUri: 'https://origin.example.com',
		clientId: '',
		title: 'Agience',
		favicon: '/favicon.png',
	}),
}));

// Import postForm after mocking runtime config so it picks up the stub URI
import { postForm } from '../api';

describe('api/postForm', () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
	});

	it('submits /auth/token to ORIGIN_URI (Origin owns identity)', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: vi.fn().mockResolvedValue({ token: 'abc' }),
		});
		vi.stubGlobal('fetch', fetchMock);

		const form = new URLSearchParams({ code: '123' });
		const result = await postForm('/auth/token', form);

		expect(fetchMock).toHaveBeenCalledWith('https://origin.example.com/auth/token', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded',
			},
			body: form,
		});
		expect(result).toEqual({ token: 'abc' });
	});

	it('submits the /auth/authorizer/* carve-out to ORIGIN_URI', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: vi.fn().mockResolvedValue({}),
		});
		vi.stubGlobal('fetch', fetchMock);

		await postForm('/auth/authorizer/complete-oauth', new URLSearchParams());
		expect(fetchMock).toHaveBeenLastCalledWith(
			'https://api.example.com/auth/authorizer/complete-oauth',
			expect.any(Object),
		);
	});

	it('submits /auth/passkey/* to ORIGIN_URI (moved in 1.1b)', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: vi.fn().mockResolvedValue({}),
		});
		vi.stubGlobal('fetch', fetchMock);

		await postForm('/auth/passkey/login-options', new URLSearchParams());
		expect(fetchMock).toHaveBeenLastCalledWith(
			'https://origin.example.com/auth/passkey/login-options',
			expect.any(Object),
		);
	});

	it('throws when the backend returns a non-ok response', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			json: vi.fn().mockResolvedValue({ detail: 'invalid' }),
		});
		vi.stubGlobal('fetch', fetchMock);

		const form = new URLSearchParams();

		await expect(postForm('/auth/token', form)).rejects.toThrow('invalid');
	});
});
