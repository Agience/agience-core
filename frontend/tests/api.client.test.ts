import { describe, it, expect, vi } from 'vitest';
import { setupApiMocks } from './utils/helpers';

describe('tests/utils/helpers', () => {
	it('setupApiMocks resets all provided API mocks when methods exist', () => {
		const api = {
			get: vi.fn().mockName('get'),
			post: vi.fn().mockName('post'),
			patch: vi.fn().mockName('patch'),
			del: vi.fn().mockName('del'),
			put: vi.fn().mockName('put'),
		};

		// call mock methods to ensure they register invocations
		api.get('foo');
		api.post('bar');

		setupApiMocks(api);

		expect(api.get).toHaveBeenCalledTimes(0);
		expect(api.post).toHaveBeenCalledTimes(0);
		expect(api.patch).toHaveBeenCalledTimes(0);
		expect(api.del).toHaveBeenCalledTimes(0);
		expect(api.put).toHaveBeenCalledTimes(0);
	});

	it('setupApiMocks gracefully handles missing methods', () => {
		const api = { get: vi.fn() } as Record<string, unknown>;

		expect(() => setupApiMocks(api)).not.toThrow();
	});
});
