// Vite serves assets/ as public files. Only images used on screen are requested.
const fallbackPath = 'picture/TFT.png';

export function asset(path, base = import.meta.env?.BASE_URL || '/') {
  // This local champion snapshot contains numeric LoL IDs, not TFT character IDs.
  if (!path || (path.startsWith('champion-icon/') && !/^champion-icon\/\d+\.png$/.test(path))) {
    path = fallbackPath;
  }
  return `${base.replace(/\/$/, '')}/${path.split('/').map(encodeURIComponent).join('/')}`;
}

export function fallbackImage(event) {
  const image = event.currentTarget;
  const fallback = asset(fallbackPath);
  // A missing fallback must not create a loop of failed image requests.
  if (image.getAttribute('src') !== fallback) image.setAttribute('src', fallback);
}
