const TEXT_EXTENSIONS = new Set([
  '.txt',
  '.md',
  '.markdown',
  '.json',
  '.csv',
  '.log',
])

const PDF_EXTENSION = '.pdf'
const DOCX_EXTENSION = '.docx'

export const GRAPH_DOCUMENT_ACCEPT = '.txt,.md,.markdown,.json,.csv,.pdf,.docx'

function getExtension(fileName: string): string {
  const idx = fileName.lastIndexOf('.')
  return idx === -1 ? '' : fileName.slice(idx).toLowerCase()
}

async function readTextFile(file: File): Promise<string> {
  return (await file.text()).trim()
}

async function readPdfFile(file: File): Promise<string> {
  const pdfjs = await import('pdfjs-dist')
  const data = new Uint8Array(await file.arrayBuffer())
  const loadingTask = (pdfjs as any).getDocument({
    data,
    disableWorker: true,
  })
  const doc = await loadingTask.promise
  const chunks: string[] = []

  for (let i = 1; i <= doc.numPages; i += 1) {
    const page = await doc.getPage(i)
    const content = await page.getTextContent()
    const pageText = (content.items || [])
      .map((item: any) => (typeof item?.str === 'string' ? item.str : ''))
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim()
    if (pageText) chunks.push(pageText)
  }

  return chunks.join('\n\n').trim()
}

async function readDocxFile(file: File): Promise<string> {
  const mammoth = await import('mammoth')
  const { value } = await mammoth.extractRawText({
    arrayBuffer: await file.arrayBuffer(),
  })
  return (value || '').replace(/\r\n/g, '\n').trim()
}

export async function extractTextFromDocument(file: File): Promise<string> {
  const ext = getExtension(file.name)

  if (TEXT_EXTENSIONS.has(ext)) return readTextFile(file)
  if (ext === PDF_EXTENSION) return readPdfFile(file)
  if (ext === DOCX_EXTENSION) return readDocxFile(file)

  throw new Error(`Unsupported file type: ${ext || 'unknown'}`)
}
