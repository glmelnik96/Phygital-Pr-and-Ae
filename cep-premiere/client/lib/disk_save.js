// Save a Blob to a stable disk path inside %LOCALAPPDATA%/PhygitalStudio/downloads-panel/.
// Requires Node-enabled CEF (manifest --enable-nodejs).

// Phygital периодически возвращает blob с Content-Type='image/png', но
// в байтах лежит JPEG (или наоборот). Если расширение файла не совпадает с
// magic-байтами — Pr importFiles падает с "Unsupported format or damaged file".
// Sniff делаем по первым байтам и переименовываем расширение если нужно.
function _sniffExt(buf) {
  if (!buf || buf.length < 12) return null;
  // PNG: 89 50 4E 47 0D 0A 1A 0A
  if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4E && buf[3] === 0x47) return 'png';
  // JPEG: FF D8 FF
  if (buf[0] === 0xFF && buf[1] === 0xD8 && buf[2] === 0xFF) return 'jpg';
  // WEBP: RIFF....WEBP
  if (buf[0] === 0x52 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x46 &&
      buf[8] === 0x57 && buf[9] === 0x45 && buf[10] === 0x42 && buf[11] === 0x50) return 'webp';
  // GIF: GIF87a / GIF89a
  if (buf[0] === 0x47 && buf[1] === 0x49 && buf[2] === 0x46) return 'gif';
  // MP4/MOV: ?? ?? ?? ?? 66 74 79 70 (ftyp box at offset 4)
  if (buf[4] === 0x66 && buf[5] === 0x74 && buf[6] === 0x79 && buf[7] === 0x70) {
    // ftyp brand at offset 8: 'qt  ' → mov, иначе mp4
    if (buf[8] === 0x71 && buf[9] === 0x74) return 'mov';
    return 'mp4';
  }
  // WEBM/MKV: 1A 45 DF A3 (EBML)
  if (buf[0] === 0x1A && buf[1] === 0x45 && buf[2] === 0xDF && buf[3] === 0xA3) return 'webm';
  return null;
}

export async function saveBlobToDisk(blob, filename) {
  const fs = require('fs');
  const path = require('path');
  const os = require('os');
  const dir = path.join(process.env.LOCALAPPDATA || os.tmpdir(), 'PhygitalStudio', 'downloads-panel');
  fs.mkdirSync(dir, { recursive: true });
  const buf = Buffer.from(await blob.arrayBuffer());
  // Override extension based on actual magic bytes. Content-Type от Phygital
  // может врать (image/png + JPEG bytes — реальный случай). Pr importFiles
  // валидирует по magic и не принимает mismatch.
  const sniffed = _sniffExt(buf);
  let finalName = filename;
  if (sniffed) {
    const base = filename.replace(/\.[^.]+$/, '');
    finalName = base + '.' + sniffed;
  }
  const out = path.join(dir, finalName);
  fs.writeFileSync(out, buf);
  return out;
}

// Map MIME type to filename extension. Returns 'bin' for unknown types.
const MIME_EXT = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
  'video/mp4': 'mp4',
  'video/quicktime': 'mov',
  'audio/mpeg': 'mp3',
  'audio/wav': 'wav',
};

export function mimeToExt(mime) {
  if (!mime) return 'bin';
  return MIME_EXT[mime.toLowerCase()] || 'bin';
}

// Convert a native disk path to a file:// URL that CEF can render in <img>.
// Windows: 'C:\\Users\\Глеб\\...\\x.png' → 'file:///C:/Users/%D0%93.../x.png'.
// encodeURI handles spaces and Cyrillic; we keep '/' and ':' intact.
export function localPathToFileUrl(p) {
  if (!p) return null;
  const norm = String(p).replace(/\\/g, '/');
  // encodeURI оставляет '/', ':', '?', '#', '&' — для пути этого достаточно,
  // но '#' и '?' в имени файла сломают URL. Экранируем их явно.
  const enc = encodeURI(norm).replace(/#/g, '%23').replace(/\?/g, '%3F');
  return 'file:///' + enc.replace(/^\/+/, '');
}

// Extension whitelist for renderable thumbnails. Видео в <img> не отрендерится,
// поэтому показываем только статичные форматы.
const RENDERABLE_EXT = new Set(['png','jpg','jpeg','webp','gif','bmp']);

export function isRenderableImagePath(p) {
  if (!p) return false;
  const ext = String(p).split('.').pop().toLowerCase();
  return RENDERABLE_EXT.has(ext);
}
