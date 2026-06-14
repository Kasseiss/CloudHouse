import { useState, useEffect, useCallback } from 'react'
import { Table, Button, Space, Modal, message, Empty } from 'antd'
import { DeleteOutlined, UndoOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getTrashList, restoreFile, permanentDelete, emptyTrash, getTrashStats } from '../api/files'
import dayjs from 'dayjs'

interface FileItem {
  id: number
  name: string
  file_size: number
  mime_type: string
  is_dir: boolean
  deleted_at: string | null
  updated_at: string
}

export default function RecycleBinPage() {
  const [files, setFiles] = useState<FileItem[]>([])
  const [loading, setLoading] = useState(false)

  const fetchTrash = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getTrashList()
      setFiles(res.data || [])
    } catch {
      // handled
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTrash() }, [fetchTrash])

  const handleRestore = async (id: number) => {
    await restoreFile(id)
    message.success('已恢复')
    fetchTrash()
  }

  const handlePermanentDelete = (id: number) => {
    Modal.confirm({
      title: '确认永久删除',
      icon: <ExclamationCircleOutlined />,
      content: '此操作不可恢复！',
      okType: 'danger',
      onOk: async () => {
        await permanentDelete(id)
        message.success('已永久删除')
        fetchTrash()
      },
    })
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
    return (bytes / 1073741824).toFixed(2) + ' GB'
  }

  const columns: ColumnsType<FileItem> = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, r: FileItem) => (
        <span>
          {r.is_dir ? '📁 ' : '📄 '}{name}
        </span>
      ),
    },
    {
      title: '大小', dataIndex: 'file_size', key: 'size',
      render: (s: number, r: FileItem) => r.is_dir ? '-' : formatBytes(s), width: 120,
    },
    {
      title: '删除时间', dataIndex: 'deleted_at', key: 'time',
      render: (t: string) => t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-', width: 180,
    },
    {
      title: '操作', key: 'action', width: 220,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<UndoOutlined />} onClick={() => handleRestore(record.id)}>恢复</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handlePermanentDelete(record.id)}>永久删除</Button>
        </Space>
      ),
    },
  ]

  const handleEmptyTrash = async () => {
    let stats: any = null
    try {
      const res: any = await getTrashStats()
      stats = res.data
    } catch { /* ignore */ }

    const formatSize = (bytes: number) => {
      if (bytes < 1024) return bytes + ' B'
      if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
      if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
      return (bytes / 1073741824).toFixed(2) + ' GB'
    }

    Modal.confirm({
      title: '确认清空回收站',
      icon: <ExclamationCircleOutlined />,
      content: stats
        ? `将永久删除 ${stats.total_items} 个项目（${stats.file_count} 个文件，${stats.folder_count} 个文件夹），释放 ${formatSize(stats.total_size)} 空间。此操作不可恢复！`
        : '将永久删除回收站中的所有文件，此操作不可恢复！',
      okType: 'danger',
      okText: '确认清空',
      onOk: async () => {
        await emptyTrash()
        message.success('回收站已清空')
        fetchTrash()
      },
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3>🗑 回收站</h3>
        {files.length > 0 && (
          <Button danger icon={<DeleteOutlined />} onClick={handleEmptyTrash}>清空回收站</Button>
        )}
      </div>
      <Table rowKey="id" columns={columns} dataSource={files} loading={loading}
        pagination={{ pageSize: 50 }}
        locale={{ emptyText: <Empty description="回收站为空" /> }}
      />
    </div>
  )
}
