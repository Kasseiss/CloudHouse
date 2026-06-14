import { useState, useEffect } from 'react'
import { Drawer, Descriptions, Tag, Button, Space, Image, Input, List, Typography, Popconfirm, message } from 'antd'
import { DownloadOutlined, ShareAltOutlined, EditOutlined, DeleteOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getFileNotes, addFileNote, deleteFileNote } from '../api/files'

const { Text } = Typography

interface FileItem {
  id: number; name: string; file_size: number; mime_type: string
  is_dir: boolean; parent_id: number | null; created_at: string; updated_at: string
  download_count?: number
  last_accessed_at?: string
}

interface Props {
  file: FileItem | null
  open: boolean
  onClose: () => void
  onPreview: (f: FileItem) => void
  onDownload: (f: FileItem) => void
  onShare: (f: FileItem) => void
  onRename: (f: FileItem) => void
  onDelete: (id: number) => void
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
  return (bytes / 1073741824).toFixed(2) + ' GB'
}

function getTypeColor(mime: string): string {
  if (mime.startsWith('image/')) return 'green'
  if (mime.startsWith('video/')) return 'purple'
  if (mime.startsWith('audio/')) return 'orange'
  if (mime.includes('pdf')) return 'red'
  if (mime.includes('text') || mime.includes('json') || mime.includes('xml')) return 'blue'
  if (mime.includes('word') || mime.includes('excel') || mime.includes('powerpoint')) return 'cyan'
  if (mime.includes('zip') || mime.includes('rar') || mime.includes('7z')) return 'gold'
  return 'default'
}

export default function FileDetail({ file, open, onClose, onPreview, onDownload, onShare, onRename, onDelete }: Props) {
  const [notes, setNotes] = useState<any[]>([])
  const [newNote, setNewNote] = useState('')

  useEffect(() => {
    if (file && !file.is_dir) {
      getFileNotes(file.id).then((res: any) => setNotes(res.data || [])).catch(() => setNotes([]))
    } else {
      setNotes([])
    }
    setNewNote('')
  }, [file])

  const handleAddNote = async () => {
    if (!file || !newNote.trim()) return
    await addFileNote(file.id, newNote.trim())
    setNewNote('')
    const res: any = await getFileNotes(file.id)
    setNotes(res.data || [])
    message.success('备注已添加')
  }

  const handleDeleteNote = async (noteId: number) => {
    if (!file) return
    await deleteFileNote(noteId)
    const res: any = await getFileNotes(file.id)
    setNotes(res.data || [])
    message.success('备注已删除')
  }

  if (!file) return null

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={file.is_dir ? '📁 文件夹信息' : '📄 文件详情'}
      width={400}
      extra={
        <Space>
          {!file.is_dir && <Button icon={<EyeOutlined />} onClick={() => onPreview(file)}>预览</Button>}
          {!file.is_dir && <Button icon={<DownloadOutlined />} onClick={() => onDownload(file)}>下载</Button>}
          <Button icon={<ShareAltOutlined />} onClick={() => onShare(file)}>分享</Button>
          <Button icon={<EditOutlined />} onClick={() => onRename(file)}>重命名</Button>
          <Button danger icon={<DeleteOutlined />} onClick={() => onDelete(file.id)}>删除</Button>
        </Space>
      }
    >
      {!file.is_dir && file.mime_type.startsWith('image/') && (
        <Image src={`/api/v1/files/${file.id}/preview`} alt={file.name}
          style={{ maxWidth: '100%', maxHeight: 200, marginBottom: 16, borderRadius: 8 }} />
      )}
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="名称">{file.name}</Descriptions.Item>
        <Descriptions.Item label="类型">
          {file.is_dir ? '文件夹' : <Tag color={getTypeColor(file.mime_type)}>{file.mime_type}</Tag>}
        </Descriptions.Item>
        {!file.is_dir && (
          <Descriptions.Item label="大小">{formatBytes(file.file_size)}</Descriptions.Item>
        )}
        <Descriptions.Item label="创建时间">{dayjs(file.created_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
        <Descriptions.Item label="修改时间">{dayjs(file.updated_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
        {!file.is_dir && <Descriptions.Item label="下载次数">{file.download_count || 0} 次</Descriptions.Item>}
        {file.last_accessed_at && (
          <Descriptions.Item label="最近访问">{dayjs(file.last_accessed_at).format('MM-DD HH:mm:ss')}</Descriptions.Item>
        )}
      </Descriptions>

      {/* File Notes */}
      {!file.is_dir && (
        <div style={{ marginTop: 24 }}>
          <Text strong style={{ marginBottom: 8, display: 'block' }}>📝 备注 ({notes.length})</Text>
          <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
            <Input
              placeholder="添加备注..."
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              onPressEnter={handleAddNote}
            />
            <Button icon={<PlusOutlined />} onClick={handleAddNote}>添加</Button>
          </Space.Compact>
          {notes.length > 0 && (
            <List
              size="small"
              dataSource={notes}
              renderItem={(item: any) => (
                <List.Item
                  actions={[
                    <Popconfirm key="del" title="删除这条备注？" onConfirm={() => handleDeleteNote(item.id)}>
                      <Button type="link" size="small" danger>删除</Button>
                    </Popconfirm>
                  ]}
                >
                  <div>
                    <Text style={{ fontSize: 13 }}>{item.content}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 10 }}>{dayjs(item.created_at).format('MM-DD HH:mm')}</Text>
                  </div>
                </List.Item>
              )}
            />
          )}
        </div>
      )}
    </Drawer>
  )
}
