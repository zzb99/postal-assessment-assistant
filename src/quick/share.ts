type SharePlatform = { share?: (data: ShareData) => Promise<void>; canShare?: (data: ShareData) => boolean };

export async function sharePreparedFile(file: File, platform: SharePlatform = navigator): Promise<'shared' | 'unsupported' | 'cancelled'> {
  if (!platform.share || !platform.canShare || !platform.canShare({ files: [file] })) return 'unsupported';
  try { await platform.share({ files: [file], title: file.name }); return 'shared'; }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled'; throw error; }
}

export function saveFile(file: File): void {
  const url = URL.createObjectURL(file);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = file.name;
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export async function imageFromPdf(file: File): Promise<File> {
  const pdfjs = await import('pdfjs-dist');
  const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  const task = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
  try {
    const pdf = await task.promise;
    if (pdf.numPages !== 1) throw new Error('文书不是单页，不能生成分享图片。');
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale: 2 });
    const canvas = document.createElement('canvas'); canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
    const context = canvas.getContext('2d'); if (!context) throw new Error('当前浏览器不能生成图片，请下载PDF。');
    await page.render({ canvas, canvasContext: context, viewport }).promise;
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error('图片生成失败')), 'image/png'));
    return new File([blob], file.name.replace(/\.pdf$/i, '.png'), { type: 'image/png' });
  } finally { await task.destroy(); }
}
