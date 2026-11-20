// The preferences of the user for the first render of each page: see hooks.server.ts
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ locals }) => ({ preferences: locals.preferences });
