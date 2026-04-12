import { describe, it, expect, vi, afterEach } from 'vitest';

vi.mock('../../config/runtime', () => ({
	getRuntimeConfig: () => ({
		backendUri: 'https://api.example.com',
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

	it('submits form data to the configured backend and returns JSON', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: vi.fn().mockResolvedValue({ token: 'abc' }),
		});
		vi.stubGlobal('fetch', fetchMock);

		const form = new URLSearchParams({ code: '123' });
		const result = await postForm('/auth/token', form);

		expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/auth/token', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded',
			},
			body: form,
		});
		expect(result).toEqual({ token: 'abc' });
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
