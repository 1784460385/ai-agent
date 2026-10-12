const KEY_STORAGE = 'deepseek_api_key';
const MODEL_STORAGE = 'deepseek_model';
const OWNER_STORAGE = 'deepseek_api_key_owner';

export function readApiKey(userId: number): { apiKey: string; modelName: string } {
  if (sessionStorage.getItem(OWNER_STORAGE) !== String(userId)) {
    return { apiKey: '', modelName: 'deepseek-flash' };
  }
  return {
    apiKey: sessionStorage.getItem(KEY_STORAGE) || '',
    modelName: sessionStorage.getItem(MODEL_STORAGE) || 'deepseek-flash',
  };
}

export function saveApiKey(userId: number, apiKey: string, modelName: string) {
  sessionStorage.setItem(OWNER_STORAGE, String(userId));
  sessionStorage.setItem(KEY_STORAGE, apiKey);
  sessionStorage.setItem(MODEL_STORAGE, modelName);
}

export function clearApiKey() {
  sessionStorage.removeItem(KEY_STORAGE);
  sessionStorage.removeItem(MODEL_STORAGE);
  sessionStorage.removeItem(OWNER_STORAGE);
}

export function clearApiKeyIfOwnerChanged(userId: number) {
  const owner = sessionStorage.getItem(OWNER_STORAGE);
  if (owner && owner !== String(userId)) {
    clearApiKey();
  }
}
