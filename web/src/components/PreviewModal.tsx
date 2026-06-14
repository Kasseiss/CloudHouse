import { useState, useEffect } from 'react'
import { Modal, Image, Button, Space, Typography, Spin } from 'antd'
import { DownloadOutlined, CloseOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Props {
  open: boolean
  file: { id: number; name: string; mime_type: string; file_size: number } | null
  onClose: () => void
  siblingImages?: { id: number; name: string }[]
  onNavigate?: (fileId: number) => void
}

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 'image/svg+xml']
const VIDEO_TYPES = ['video/mp4', 'video/webm', 'video/ogg', 'video/x-msvideo', 'video/x-matroska', 'video/quicktime']
const AUDIO_TYPES = ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/flac']
const TEXT_TYPES = ['text/plain', 'text/csv']
const CODE_TYPES = ['text/html', 'text/css', 'application/json', 'application/xml', 'application/javascript',
  'text/x-python', 'text/x-java', 'text/x-go', 'text/x-rust', 'application/typescript']
const PDF_TYPE = 'application/pdf'

const EXT_CODE_MAP: Record<string, boolean> = {
  '.py': true, '.js': true, '.ts': true, '.tsx': true, '.jsx': true,
  '.json': true, '.html': true, '.css': true, '.scss': true, '.less': true,
  '.java': true, '.go': true, '.rs': true, '.cpp': true, '.c': true, '.h': true,
  '.xml': true, '.yaml': true, '.yml': true, '.toml': true, '.ini': true, '.cfg': true,
  '.sh': true, '.bash': true, '.ps1': true, '.sql': true, '.rb': true, '.php': true,
  '.swift': true, '.kt': true, '.scala': true, '.r': true, '.m': true,
  '.md': true, '.markdown': true,
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
  return (bytes / 1073741824).toFixed(2) + ' GB'
}

function renderMarkdown(md: string): string {
  let html = md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre style="background:#1e1e1e;color:#d4d4d4;padding:12px;border-radius:6px;overflow:auto"><code>$2</code></pre>')
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:2px 6px;border-radius:4px;font-size:0.9em">$1</code>')
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h4 style="margin:8px 0">$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3 style="margin:10px 0">$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2 style="margin:12px 0">$1</h2>')
  // Bold/Italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:#1677ff">$1</a>')
  // Images
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%;border-radius:8px;margin:8px 0">')
  // Unordered lists
  html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul style="padding-left:20px;margin:8px 0">$&</ul>')
  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid #e8e8e8;margin:16px 0">')
  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, '<br><br>')
  return html
}

function MarkdownPreview({ url }: { url: string }) {
  const [html, setHtml] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
      .then(r => r.text())
      .then(md => { setHtml(renderMarkdown(md)); setLoading(false) })
      .catch(() => setLoading(false))
  }, [url])

  if (loading) return <Spin style={{ display: 'block', padding: 40 }} />
  return (
    <div
      style={{ padding: 16, lineHeight: 1.8, fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif', maxHeight: '60vh', overflow: 'auto' }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function CodePreview({ url }: { url: string }) {
  const [code, setCode] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setCode(null)
    fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
      .then(r => r.text())
      .then(text => { setCode(text); setLoading(false) })
      .catch(() => setLoading(false))
  }, [url])

  if (loading) return <Spin style={{ display: 'block', padding: 40 }} />
  if (code === null) return <Typography.Text type="secondary">加载失败</Typography.Text>

  const lines = code.split('\n')
  const pad = String(lines.length).length

  return (
    <div style={{
      background: '#1e1e1e', borderRadius: 8, overflow: 'auto', maxHeight: '60vh',
      fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace", fontSize: 12, lineHeight: 1.7,
    }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? '#1e1e1e' : '#252525' }}>
              <td style={{
                width: 40, textAlign: 'right', padding: '0 12px', color: '#858585',
                userSelect: 'none', borderRight: '1px solid #333', verticalAlign: 'top',
              }}>
                {String(i + 1).padStart(pad, ' ')}
              </td>
              <td style={{ padding: '0 12px', color: '#d4d4d4', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {line || ' '}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function PreviewModal({ open, file, onClose, siblingImages, onNavigate }: Props) {
  if (!file) return null

  const previewUrl = `/api/v1/files/${file.id}/preview`
  const downloadUrl = `/api/v1/files/${file.id}/download`
  const mime = file.mime_type

  const renderContent = () => {
    if (IMAGE_TYPES.includes(mime)) {
      const siblings = siblingImages || []
      const currentIdx = siblings.findIndex(s => s.id === file.id)
      const prev = currentIdx > 0 ? siblings[currentIdx - 1] : null
      const next = currentIdx < siblings.length - 1 ? siblings[currentIdx + 1] : null
      return (
        <div style={{ textAlign: 'center', position: 'relative' }}>
          <Image src={previewUrl} alt={file.name} style={{ maxHeight: '60vh' }} />
          {(prev || next) && (
            <div style={{ marginTop: 12, display: 'flex', justifyContent: 'center', gap: 16, alignItems: 'center' }}>
              <Button disabled={!prev} onClick={() => prev && onNavigate?.(prev.id)}>← 上一张</Button>
              <span style={{ color: '#999', fontSize: 12 }}>{currentIdx + 1} / {siblings.length}</span>
              <Button disabled={!next} onClick={() => next && onNavigate?.(next.id)}>下一张 →</Button>
            </div>
          )}
        </div>
      )
    }
    if (VIDEO_TYPES.includes(mime)) {
      return (
        <video controls style={{ maxWidth: '100%', maxHeight: '60vh' }}>
          <source src={previewUrl} type={mime} />
          您的浏览器不支持播放此视频
        </video>
      )
    }
    if (AUDIO_TYPES.includes(mime)) {
      return (
        <audio controls style={{ width: '100%' }}>
          <source src={previewUrl} type={mime} />
        </audio>
      )
    }
    if (PDF_TYPE === mime) {
      return (
        <iframe src={previewUrl} style={{ width: '100%', height: '65vh', border: 'none' }} title={file.name} />
      )
    }
    if (TEXT_TYPES.includes(mime)) {
      return (
        <iframe src={previewUrl} style={{ width: '100%', height: '60vh', border: '1px solid #f0f0f0' }} title={file.name} />
      )
    }
    if (file.name.endsWith('.md') || file.name.endsWith('.markdown') || mime === 'text/markdown') {
      return <MarkdownPreview url={previewUrl} />
    }
    if (CODE_TYPES.includes(mime) || EXT_CODE_MAP[file.name.slice(file.name.lastIndexOf('.'))] || file.name.endsWith('.py') || file.name.endsWith('.js') || file.name.endsWith('.ts')) {
      return <CodePreview url={previewUrl} />
    }
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <div style={{ fontSize: 64, marginBottom: 16 }}>📄</div>
        <Text type="secondary">该文件类型不支持在线预览</Text>
        <br />
        <Text type="secondary">{mime} · {formatBytes(file.file_size)}</Text>
      </div>
    )
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={
        <Space>
          <a href={downloadUrl} download={file.name}>
            <Button type="primary" icon={<DownloadOutlined />}>下载</Button>
          </a>
          <Button icon={<CloseOutlined />} onClick={onClose}>关闭</Button>
        </Space>
      }
      width={900}
      title={file.name}
      destroyOnClose
    >
      {renderContent()}
    </Modal>
  )
}
