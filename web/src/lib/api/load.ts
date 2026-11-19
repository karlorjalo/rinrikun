// A helper for the load functions of the pages.
import { error } from '@sveltejs/kit';
import { ApiError } from './client.js';

/** Run the requests of a load function. An error of the API server gives the error page. */
export async function fromApi<T>(work: () => Promise<T>): Promise<T> {
	try {
		return await work();
	} catch (cause) {
		if (cause instanceof ApiError && cause.status === 404) error(404, 'Not found');
		if (cause instanceof ApiError) error(502, `The API server answered ${cause.status}`);
		error(502, 'The API server does not answer');
	}
}
