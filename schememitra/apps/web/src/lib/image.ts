'use client';

/**
 * Shrinks a camera photo on the device before upload (≤1600 px, JPEG, aiming under ~250 KB)
 * so it goes through on 2G. Drawing to a canvas also drops EXIF/GPS before the photo leaves
 * the phone. The server re-encodes again anyway.
 */
export async function compressPhoto(file: Blob, maxEdge = 1600, targetBytes = 250_000): Promise<Blob> {
  if (!file.type.startsWith('image/')) return file;
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  let quality = 0.82;
  let blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), 'image/jpeg', quality));
  while (blob.size > targetBytes && quality > 0.45) {
    quality -= 0.12;
    blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), 'image/jpeg', quality));
  }
  return blob;
}
