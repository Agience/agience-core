import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
	del: vi.fn(),
	put: vi.fn(),
}));

import { get } from '../api';
import { listWorkspaceArtifacts } from '../workspaces';

const mockedGet = get as unknown as ReturnType<typeof vi.fn>;

describe('api/workspaces (TypeScript helpers)', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('returns items envelope from API', async () => {
		mockedGet.mockResolvedValueOnce({
			items: [
				{ id: 'c1', content: 'Artifact 1', state: 'draft', context: '{}', collection_ids: [] },
			],
			order_version: 3,
		});

		const result = await listWorkspaceArtifacts('ws-1');

		expect(result).toEqual({
			items: [
				expect.objectContaining({ id: 'c1' }),
			],
			order_version: 3,
		});
	});
});
