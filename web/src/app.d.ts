// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			/** The preferences of the user, from the cookies */
			preferences: import('#lib/preferences.js').Preferences;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
