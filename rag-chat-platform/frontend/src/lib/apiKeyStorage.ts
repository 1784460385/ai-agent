const SELECTED_KEY = 'selected_api_key_id';
const OWNER_STORAGE = 'selected_api_key_owner';

export function readSelectedKeyId(userId: number): number | null {
  if (sessionStorage.getItem(OWNER_STORAGE) !== String(userId)) return null;
  const raw = sessionStorage.getItem(SELECTED_KEY);
  const id = Number(raw);
  return raw && id ? id : null;
}

export function saveSelectedKeyId(userId: number, keyId: number) {
  sessionStorage.setItem(OWNER_STORAGE, String(userId));
  sessionStorage.setItem(SELECTED_KEY, String(keyId));
}

export function clearApiKey() {
  sessionStorage.removeItem(SELECTED_KEY);
  sessionStorage.removeItem(OWNER_STORAGE);
}

export function clearApiKeyIfOwnerChanged(userId: number) {
  const owner = sessionStorage.getItem(OWNER_STORAGE);
  if (owner && owner !== String(userId)) {
    clearApiKey();
  }
}
